from __future__ import annotations

import argparse
import gc
import json
import math
import random
import time
try:
    from unsloth import FastModel
except Exception:
    from unsloth import FastLanguageModel as FastModel

from pathlib import Path
from typing import Any

import numpy as np
import torch
from peft import PeftModel
from transformers import Trainer, TrainerCallback, TrainingArguments

from train_najdi_sft import MaskedSFTDataCollator, load_masked_sft_records


SEED = 42
TRAIN_MAX_LENGTH = 2048
EVAL_MAX_LENGTH = 8192
EXPECTED_SFT = 16
EXPECTED_MULTI = 43
EXPECTED_TRAIN = 59
EXPECTED_EVAL = 12
GENERATION_SETTINGS = {"do_sample": False, "max_new_tokens": 384}
TARGET_MODULES = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected an object")
            rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def set_seed() -> None:
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)


def processor_and_tokenizer(processor_or_tokenizer: Any) -> tuple[Any, Any]:
    processor = processor_or_tokenizer
    tokenizer = getattr(processor_or_tokenizer, "tokenizer", processor_or_tokenizer)
    if getattr(tokenizer, "chat_template", None) is None:
        template = getattr(processor, "chat_template", None)
        if template is not None:
            tokenizer.chat_template = template
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    return processor, tokenizer


def load_base(model_path: Path, max_seq_length: int) -> tuple[Any, Any, Any]:
    model, processor_or_tokenizer = FastModel.from_pretrained(
        model_name=str(model_path),
        max_seq_length=max_seq_length,
        load_in_4bit=True,
        load_in_8bit=False,
        full_finetuning=False,
    )
    processor, tokenizer = processor_and_tokenizer(processor_or_tokenizer)
    model.eval()
    return model, processor, tokenizer


def evaluation_case(row: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    messages = row.get("messages")
    target_index = row.get("target_message_index")
    mask = row.get("message_loss_mask")
    if not isinstance(messages, list) or not messages:
        raise ValueError(f"{row.get('id')}: missing messages")
    if target_index != len(messages) - 1:
        raise ValueError(f"{row.get('id')}: target is not final")
    if mask != [0] * target_index + [1]:
        raise ValueError(f"{row.get('id')}: invalid message_loss_mask")
    context = messages[:target_index]
    target = messages[target_index]
    if target.get("role") != "assistant" or not isinstance(target.get("content"), str):
        raise ValueError(f"{row.get('id')}: invalid Gold target")
    if not context or context[-1].get("role") != "user":
        raise ValueError(f"{row.get('id')}: prompt must end at the final user")
    return context, target["content"]


def generate(model: Any, processor: Any, tokenizer: Any, context: list[dict[str, str]]) -> tuple[str, int]:
    renderer = processor if hasattr(processor, "apply_chat_template") else tokenizer
    rendered = renderer.apply_chat_template(context, tokenize=False, add_generation_prompt=True)
    if not isinstance(rendered, str):
        raise ValueError("chat template did not render text")
    inputs = tokenizer(rendered, return_tensors="pt", add_special_tokens=False, truncation=False)
    prompt_tokens = int(inputs["input_ids"].shape[-1])
    if prompt_tokens > EVAL_MAX_LENGTH:
        raise ValueError(f"evaluation prompt has {prompt_tokens} tokens; refusing to truncate")
    inputs = {key: value.to(model.device) for key, value in inputs.items()}
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            **GENERATION_SETTINGS,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    generated_ids = output[0][prompt_tokens:].tolist()
    text = tokenizer.decode(
        generated_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    ).strip()
    if not text:
        raise RuntimeError("model generated an empty response")
    return text, prompt_tokens


def benchmark(export_dir: Path, model_path: Path, output: Path, label: str, adapter: Path | None) -> None:
    set_seed()
    rows = read_jsonl(export_dir / "text_sft_eval.jsonl")
    if len(rows) != EXPECTED_EVAL:
        raise SystemExit(f"Expected {EXPECTED_EVAL} text eval rows, found {len(rows)}")
    model, processor, tokenizer = load_base(model_path, EVAL_MAX_LENGTH)
    if adapter is not None:
        if not (adapter / "adapter_model.safetensors").is_file():
            raise SystemExit(f"Adapter is missing: {adapter}")
        model = PeftModel.from_pretrained(model, str(adapter))
        model.eval()
    results = []
    started = time.perf_counter()
    for index, row in enumerate(rows, start=1):
        context, gold = evaluation_case(row)
        sample_id = str(row.get("id"))
        print(f"{label} evaluation {index}/{EXPECTED_EVAL}: {sample_id}", flush=True)
        response, prompt_tokens = generate(model, processor, tokenizer, context)
        results.append(
            {
                "id": sample_id,
                "category": row.get("evaluation_subcategory") or row.get("evaluation_category"),
                "conversation_id": row.get("conversation_id"),
                "gold": gold,
                "response": response,
                "prompt_message_count": len(context),
                "prompt_token_count": prompt_tokens,
                "gold_target_in_prompt": False,
            }
        )
    elapsed = round(time.perf_counter() - started, 2)
    write_jsonl(output, results)
    write_json(
        output.with_suffix(".meta.json"),
        {
            "label": label,
            "records": len(results),
            "seed": SEED,
            "generation_settings": GENERATION_SETTINGS,
            "same_chat_template": True,
            "gold_target_in_prompt": False,
            "adapter": str(adapter) if adapter else None,
            "elapsed_seconds": elapsed,
            "output": str(output),
        },
    )
    print(json.dumps({"label": label, "records": len(results), "elapsed_seconds": elapsed, "output": str(output)}, indent=2))
    del model
    gc.collect()
    torch.cuda.empty_cache()


class RecordDataset:
    def __init__(self, records: list[dict[str, Any]]):
        self.records = records

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.records[index]


class StopOnInvalidLoss(TrainerCallback):
    def on_log(self, args: Any, state: Any, control: Any, logs: dict[str, Any] | None = None, **kwargs: Any) -> None:
        if not logs:
            return
        for key in ("loss", "train_loss"):
            value = logs.get(key)
            if value is not None and not math.isfinite(float(value)):
                raise FloatingPointError(f"Non-finite {key} at step {state.global_step}: {value}")


def train(export_dir: Path, model_path: Path, output_dir: Path) -> None:
    set_seed()
    if output_dir.exists():
        raise SystemExit(f"Refusing to overwrite existing output: {output_dir}")
    sft = read_jsonl(export_dir / "sft.jsonl")
    multi = read_jsonl(export_dir / "multi_turn.jsonl")
    eval_rows = read_jsonl(export_dir / "text_sft_eval.jsonl")
    if (len(sft), len(multi), len(eval_rows)) != (EXPECTED_SFT, EXPECTED_MULTI, EXPECTED_EVAL):
        raise SystemExit(
            f"Expected sft={EXPECTED_SFT}, multi={EXPECTED_MULTI}, eval={EXPECTED_EVAL}; "
            f"got {len(sft)}, {len(multi)}, {len(eval_rows)}"
        )
    train_rows = sft + multi
    train_ids = {str(row.get("id")) for row in train_rows}
    eval_ids = {str(row.get("id")) for row in eval_rows}
    train_conversations = {str(row.get("conversation_id")) for row in train_rows if row.get("conversation_id")}
    eval_conversations = {str(row.get("conversation_id")) for row in eval_rows if row.get("conversation_id")}
    if train_ids & eval_ids:
        raise SystemExit(f"Train/eval ID leakage: {sorted(train_ids & eval_ids)}")
    if train_conversations & eval_conversations:
        raise SystemExit(f"Train/eval conversation leakage: {sorted(train_conversations & eval_conversations)}")
    if not torch.cuda.is_bf16_supported():
        raise SystemExit("BF16 is required but is not supported")

    model, processor_or_tokenizer = FastModel.from_pretrained(
        model_name=str(model_path),
        max_seq_length=TRAIN_MAX_LENGTH,
        load_in_4bit=True,
        load_in_8bit=False,
        full_finetuning=False,
    )
    _, tokenizer = processor_and_tokenizer(processor_or_tokenizer)
    records = load_masked_sft_records(export_dir, tokenizer, TRAIN_MAX_LENGTH)
    if len(records) != EXPECTED_TRAIN:
        raise SystemExit(f"Expected {EXPECTED_TRAIN} masked records, found {len(records)}")

    model = FastModel.get_peft_model(
        model,
        finetune_vision_layers=False,
        finetune_language_layers=True,
        finetune_attention_modules=True,
        finetune_mlp_modules=True,
        r=16,
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        random_state=SEED,
        use_gradient_checkpointing="unsloth",
    )
    model.config.use_cache = False
    args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=1.0,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=1,
        learning_rate=2e-5,
        lr_scheduler_type="linear",
        warmup_steps=0,
        logging_steps=1,
        logging_nan_inf_filter=False,
        save_strategy="no",
        bf16=True,
        fp16=False,
        optim="adamw_8bit",
        seed=SEED,
        data_seed=SEED,
        remove_unused_columns=False,
        report_to="none",
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=RecordDataset(records),
        data_collator=MaskedSFTDataCollator(tokenizer),
        callbacks=[StopOnInvalidLoss()],
    )

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    train_result = trainer.train()
    duration = time.perf_counter() - started
    loss_history = [
        {
            "step": int(entry["step"]),
            "loss": float(entry["loss"]),
            "learning_rate": float(entry["learning_rate"]),
            "epoch": float(entry["epoch"]),
        }
        for entry in trainer.state.log_history
        if "loss" in entry
    ]
    invalid_loss = any(not math.isfinite(entry["loss"]) for entry in loss_history)
    if trainer.state.global_step != EXPECTED_TRAIN:
        raise RuntimeError(f"Expected {EXPECTED_TRAIN} optimizer steps, got {trainer.state.global_step}")
    if len(loss_history) != EXPECTED_TRAIN:
        raise RuntimeError(f"Expected {EXPECTED_TRAIN} loss entries, got {len(loss_history)}")
    if invalid_loss:
        raise RuntimeError("NaN/Inf loss detected; Adapter will not be saved")

    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    if not (output_dir / "adapter_model.safetensors").is_file():
        raise RuntimeError("Adapter was not saved")
    peft_config = next(iter(model.peft_config.values()))
    losses = [entry["loss"] for entry in loss_history]
    metrics = {
        "records": EXPECTED_TRAIN,
        "source_files": {"sft.jsonl": EXPECTED_SFT, "multi_turn.jsonl": EXPECTED_MULTI},
        "excluded_from_training": [
            "direct_language.jsonl",
            "preference_pairs.jsonl",
            "text_sft_eval.jsonl",
            "tool_eval.jsonl",
            "vision_eval.jsonl",
            "runtime_agent_eval.jsonl",
            "full_archive.json",
        ],
        "epochs": 1,
        "optimizer_steps": int(trainer.state.global_step),
        "seed": SEED,
        "shuffle": True,
        "learning_rate": 2e-5,
        "scheduler": "linear",
        "batch_size": 1,
        "gradient_accumulation": 1,
        "effective_batch_size": 1,
        "precision": "bf16",
        "optimizer": "adamw_8bit",
        "max_training_length": TRAIN_MAX_LENGTH,
        "loss_mask": "final assistant Gold only; all context and prior assistants masked",
        "lora": {
            "r": int(peft_config.r),
            "alpha": int(peft_config.lora_alpha),
            "dropout": float(peft_config.lora_dropout),
            "bias": str(peft_config.bias),
            "requested_target_modules": TARGET_MODULES,
            "effective_target_modules": peft_config.target_modules,
            "base_precision": "4-bit",
            "vision": "frozen",
            "language": "trainable",
            "gradient_checkpointing": "unsloth",
        },
        "mean_loss": sum(losses) / len(losses),
        "min_loss": min(losses),
        "max_loss": max(losses),
        "first_loss": losses[0],
        "last_loss": losses[-1],
        "has_nan_or_inf": invalid_loss,
        "duration_seconds": round(duration, 2),
        "peak_vram_allocated_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 1),
        "peak_vram_reserved_mib": round(torch.cuda.max_memory_reserved() / 1024**2, 1),
        "adapter_path": str(output_dir),
        "adapter_saved": True,
        "trainer_metrics": {key: float(value) for key, value in train_result.metrics.items()},
    }
    write_jsonl(output_dir / "loss_history.jsonl", loss_history)
    write_json(output_dir / "training_metrics.json", metrics)
    print(json.dumps(metrics, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Controlled gold-v006 clean training and evaluation")
    sub = parser.add_subparsers(dest="command", required=True)
    bench = sub.add_parser("benchmark")
    bench.add_argument("--export-dir", type=Path, required=True)
    bench.add_argument("--model", type=Path, required=True)
    bench.add_argument("--label", required=True)
    bench.add_argument("--adapter", type=Path)
    bench.add_argument("--output", type=Path, required=True)
    tr = sub.add_parser("train")
    tr.add_argument("--export-dir", type=Path, required=True)
    tr.add_argument("--model", type=Path, required=True)
    tr.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "benchmark":
        benchmark(args.export_dir, args.model, args.output, args.label, args.adapter)
    else:
        train(args.export_dir, args.model, args.output_dir)


if __name__ == "__main__":
    main()
