from __future__ import annotations

try:
    from unsloth import FastModel
except Exception:
    from unsloth import FastLanguageModel as FastModel

import argparse
import gc
import json
import math
import random
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from peft import PeftModel
from transformers import Trainer, TrainingArguments

from train_najdi_sft import MaskedSFTDataCollator, load_masked_sft_records


SEED = 42
TRAIN_MAX_LENGTH = 2048
EVAL_MAX_LENGTH = 8192
GENERATION_SETTINGS = {
    "do_sample": False,
    "max_new_tokens": 384,
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(row)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _set_seed() -> None:
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)


def _processor_and_tokenizer(processor_or_tokenizer: Any) -> tuple[Any, Any]:
    processor = processor_or_tokenizer
    tokenizer = getattr(processor_or_tokenizer, "tokenizer", processor_or_tokenizer)
    if getattr(tokenizer, "chat_template", None) is None:
        template = getattr(processor, "chat_template", None)
        if template is not None:
            tokenizer.chat_template = template
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    return processor, tokenizer


def _load_base(model_path: Path) -> tuple[Any, Any, Any]:
    model, processor_or_tokenizer = FastModel.from_pretrained(
        model_name=str(model_path),
        max_seq_length=EVAL_MAX_LENGTH,
        load_in_4bit=True,
        load_in_8bit=False,
        full_finetuning=False,
    )
    processor, tokenizer = _processor_and_tokenizer(processor_or_tokenizer)
    model.eval()
    return model, processor, tokenizer


def _evaluation_case(row: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    messages = row.get("messages")
    target_index = row.get("target_message_index")
    mask = row.get("message_loss_mask")
    if not isinstance(messages, list) or not messages:
        raise ValueError(f"{row.get('id')}: missing messages")
    if target_index != len(messages) - 1:
        raise ValueError(f"{row.get('id')}: evaluation target must be the final message")
    if not isinstance(mask, list) or len(mask) != len(messages) or mask != [0] * target_index + [1]:
        raise ValueError(f"{row.get('id')}: invalid evaluation message_loss_mask")
    target = messages[target_index]
    context = messages[:target_index]
    if not isinstance(target, dict) or target.get("role") != "assistant":
        raise ValueError(f"{row.get('id')}: target is not an assistant message")
    if not context or context[-1].get("role") != "user":
        raise ValueError(f"{row.get('id')}: context must end at the final user message")
    gold = target.get("content")
    if not isinstance(gold, str) or not gold:
        raise ValueError(f"{row.get('id')}: missing expected Gold content")
    return context, gold


def _render_prompt(processor: Any, tokenizer: Any, messages: list[dict[str, str]]) -> str:
    renderer = processor if hasattr(processor, "apply_chat_template") else tokenizer
    rendered = renderer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    if not isinstance(rendered, str):
        raise ValueError("chat template did not render a string")
    return rendered


def _generate(
    model: Any,
    processor: Any,
    tokenizer: Any,
    messages: list[dict[str, str]],
) -> tuple[str, int]:
    rendered = _render_prompt(processor, tokenizer, messages)
    inputs = tokenizer(
        rendered,
        return_tensors="pt",
        add_special_tokens=False,
        truncation=False,
    )
    prompt_tokens = int(inputs["input_ids"].shape[-1])
    if prompt_tokens > EVAL_MAX_LENGTH:
        raise ValueError(
            f"evaluation prompt has {prompt_tokens} tokens and would exceed "
            f"EVAL_MAX_LENGTH={EVAL_MAX_LENGTH}; "
            "refusing to truncate context"
        )
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


def _evaluate(
    export_dir: Path,
    model_path: Path,
    output_path: Path,
    adapter: Path | None,
    base_results_path: Path | None,
) -> None:
    _set_seed()
    rows = _read_jsonl(export_dir / "evaluation_holdout.jsonl")
    if len(rows) != 14:
        raise SystemExit(f"Expected 14 evaluation records, found {len(rows)}")

    base_by_id: dict[str, dict[str, Any]] = {}
    if adapter is not None:
        if base_results_path is None or not base_results_path.is_file():
            raise SystemExit("Trained evaluation requires the completed Base benchmark file")
        base_rows = _read_jsonl(base_results_path)
        if len(base_rows) != 14:
            raise SystemExit(f"Expected 14 Base benchmark rows, found {len(base_rows)}")
        base_by_id = {str(row["id"]): row for row in base_rows}
        if len(base_by_id) != 14:
            raise SystemExit("Base benchmark contains duplicate IDs")

    model, processor, tokenizer = _load_base(model_path)
    model_label = "base"
    if adapter is not None:
        if not (adapter / "adapter_model.safetensors").is_file():
            raise SystemExit(f"Adapter is missing: {adapter}")
        model = PeftModel.from_pretrained(model, str(adapter))
        model.eval()
        model_label = "trained_epoch1"

    results: list[dict[str, Any]] = []
    started = time.perf_counter()
    for index, row in enumerate(rows, start=1):
        context, expected_gold = _evaluation_case(row)
        sample_id = str(row.get("id"))
        print(f"{model_label} evaluation {index}/14: {sample_id}", flush=True)
        generated, prompt_tokens = _generate(model, processor, tokenizer, context)
        result = {
            "id": sample_id,
            "conversation_id": row.get("conversation_id"),
            "expected_gold": expected_gold,
            "base_output": generated if adapter is None else base_by_id[sample_id]["base_output"],
            "prompt_message_count": len(context),
            "prompt_token_count": prompt_tokens,
        }
        if adapter is not None:
            base_row = base_by_id[sample_id]
            if (
                base_row.get("conversation_id") != result["conversation_id"]
                or base_row.get("expected_gold") != expected_gold
            ):
                raise RuntimeError(f"Base benchmark metadata mismatch for {sample_id}")
            result["trained_output"] = generated
        results.append(result)

    elapsed = round(time.perf_counter() - started, 2)
    if len(results) != 14:
        raise RuntimeError("Evaluation did not complete all 14 records")
    _write_jsonl(output_path, results)
    _write_json(
        output_path.with_suffix(".meta.json"),
        {
            "model": model_label,
            "records": 14,
            "seed": SEED,
            "generation_settings": GENERATION_SETTINGS,
            "max_context_tokens": EVAL_MAX_LENGTH,
            "elapsed_seconds": elapsed,
            "adapter": str(adapter) if adapter is not None else None,
            "gold_target_in_prompt": False,
            "output": str(output_path),
        },
    )
    print(json.dumps({"records": 14, "elapsed_seconds": elapsed, "output": str(output_path)}, indent=2))
    del model
    gc.collect()
    torch.cuda.empty_cache()


class _RecordDataset:
    def __init__(self, records: list[dict[str, Any]]):
        self.records = records

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.records[index]


def _train(export_dir: Path, model_path: Path, output_dir: Path) -> None:
    _set_seed()
    if output_dir.exists():
        raise SystemExit(f"Refusing to overwrite existing Adapter directory: {output_dir}")

    sft_rows = _read_jsonl(export_dir / "sft.jsonl")
    multi_rows = _read_jsonl(export_dir / "multi_turn.jsonl")
    evaluation_rows = _read_jsonl(export_dir / "evaluation_holdout.jsonl")
    if (len(sft_rows), len(multi_rows), len(evaluation_rows)) != (14, 26, 14):
        raise SystemExit(
            "Expected sft=14, multi_turn=26, evaluation=14; got "
            f"{len(sft_rows)}, {len(multi_rows)}, {len(evaluation_rows)}"
        )
    train_ids = {row.get("id") for row in sft_rows + multi_rows}
    eval_ids = {row.get("id") for row in evaluation_rows}
    train_conversations = {row.get("conversation_id") for row in sft_rows + multi_rows}
    eval_conversations = {row.get("conversation_id") for row in evaluation_rows}
    if train_ids & eval_ids:
        raise SystemExit(f"Train/evaluation ID leakage: {sorted(train_ids & eval_ids)}")
    if train_conversations & eval_conversations:
        raise SystemExit("Train/evaluation conversation leakage detected")

    model, processor_or_tokenizer = FastModel.from_pretrained(
        model_name=str(model_path),
        max_seq_length=TRAIN_MAX_LENGTH,
        load_in_4bit=True,
        load_in_8bit=False,
        full_finetuning=False,
    )
    _, tokenizer = _processor_and_tokenizer(processor_or_tokenizer)
    records = load_masked_sft_records(export_dir, tokenizer, TRAIN_MAX_LENGTH)
    if len(records) != 40:
        raise SystemExit(f"Expected exactly 40 masked training records, found {len(records)}")

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

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=1.0,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=1,
        learning_rate=2e-5,
        warmup_steps=0,
        logging_steps=1,
        save_strategy="no",
        bf16=torch.cuda.is_bf16_supported(),
        fp16=not torch.cuda.is_bf16_supported(),
        optim="adamw_8bit",
        seed=SEED,
        data_seed=SEED,
        remove_unused_columns=False,
        report_to="none",
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=_RecordDataset(records),
        data_collator=MaskedSFTDataCollator(tokenizer),
    )

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    train_result = trainer.train()
    duration_seconds = time.perf_counter() - started

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
    if trainer.state.global_step != 40:
        raise RuntimeError(f"Expected 40 optimizer steps, got {trainer.state.global_step}")
    if len(loss_history) != 40:
        raise RuntimeError(f"Expected 40 step losses, got {len(loss_history)}")
    if invalid_loss:
        raise RuntimeError("Training produced NaN/Inf loss; Adapter will not be saved")

    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    adapter_saved = (output_dir / "adapter_model.safetensors").is_file()
    if not adapter_saved:
        raise RuntimeError("Training completed but adapter_model.safetensors was not saved")

    peft_config = next(iter(model.peft_config.values()))
    target_modules = peft_config.target_modules
    if not isinstance(target_modules, str):
        target_modules = sorted(target_modules)
    metrics = {
        "records": 40,
        "source_files": {"sft.jsonl": 14, "multi_turn.jsonl": 26},
        "excluded_from_training": [
            "evaluation_holdout.jsonl",
            "preference_pairs.jsonl",
            "full_archive.json",
            "direct_language.jsonl",
        ],
        "num_train_epochs": 1.0,
        "optimizer_steps": int(trainer.state.global_step),
        "seed": SEED,
        "shuffle": True,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 1,
        "effective_batch_size": 1,
        "learning_rate": 2e-5,
        "optimizer": "adamw_8bit",
        "precision": "bf16" if torch.cuda.is_bf16_supported() else "fp16",
        "max_length": TRAIN_MAX_LENGTH,
        "loss_mask": "final assistant Gold content only; context and previous assistants masked",
        "lora": {
            "r": int(peft_config.r),
            "alpha": int(peft_config.lora_alpha),
            "dropout": float(peft_config.lora_dropout),
            "bias": str(peft_config.bias),
            "target_modules": target_modules,
            "load_in_4bit": True,
            "vision_layers": "frozen",
            "language_layers": "trainable",
            "gradient_checkpointing": "unsloth",
        },
        "first_loss": loss_history[0]["loss"],
        "last_loss": loss_history[-1]["loss"],
        "min_loss": min(entry["loss"] for entry in loss_history),
        "max_loss": max(entry["loss"] for entry in loss_history),
        "has_nan_or_inf": invalid_loss,
        "peak_vram_allocated_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 1),
        "peak_vram_reserved_mib": round(torch.cuda.max_memory_reserved() / 1024**2, 1),
        "duration_seconds": round(duration_seconds, 2),
        "adapter_saved": adapter_saved,
        "adapter_path": str(output_dir),
        "trainer_metrics": {key: float(value) for key, value in train_result.metrics.items()},
    }
    _write_jsonl(output_dir / "loss_history.jsonl", loss_history)
    _write_json(output_dir / "training_metrics.json", metrics)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


def _repair_metrics(output_dir: Path) -> None:
    metrics_path = output_dir / "training_metrics.json"
    adapter_config_path = output_dir / "adapter_config.json"
    if not metrics_path.is_file() or not adapter_config_path.is_file():
        raise SystemExit("Adapter metrics/config files are missing")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    adapter_config = json.loads(adapter_config_path.read_text(encoding="utf-8"))
    metrics["lora"]["target_modules"] = adapter_config["target_modules"]
    _write_json(metrics_path, metrics)
    print(json.dumps({"repaired": str(metrics_path), "target_modules": adapter_config["target_modules"]}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Controlled NajdiLab gold-v004 benchmark, SFT, and evaluation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    base = subparsers.add_parser("benchmark-base")
    base.add_argument("--export-dir", type=Path, required=True)
    base.add_argument("--model", type=Path, required=True)
    base.add_argument("--output", type=Path, required=True)

    train = subparsers.add_parser("train")
    train.add_argument("--export-dir", type=Path, required=True)
    train.add_argument("--model", type=Path, required=True)
    train.add_argument("--output-dir", type=Path, required=True)

    trained = subparsers.add_parser("evaluate-trained")
    trained.add_argument("--export-dir", type=Path, required=True)
    trained.add_argument("--model", type=Path, required=True)
    trained.add_argument("--adapter", type=Path, required=True)
    trained.add_argument("--base-results", type=Path, required=True)
    trained.add_argument("--output", type=Path, required=True)

    repair = subparsers.add_parser("repair-metrics")
    repair.add_argument("--output-dir", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "benchmark-base":
        _evaluate(args.export_dir, args.model, args.output, None, None)
    elif args.command == "train":
        _train(args.export_dir, args.model, args.output_dir)
    elif args.command == "evaluate-trained":
        _evaluate(
            args.export_dir,
            args.model,
            args.output,
            args.adapter,
            args.base_results,
        )
    else:
        _repair_metrics(args.output_dir)


if __name__ == "__main__":
    main()
