from __future__ import annotations

# Retained for historical validation imports, retired as an executable.
if __name__ == '__main__':
    raise SystemExit('Training is retired in NajdiLab. Export a reviewed dataset for external Unsloth.')


import argparse
import json
import math
import random
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from unsloth import FastModel
from transformers import Trainer, TrainingArguments

from train_najdi_sft import MaskedSFTDataCollator, load_masked_sft_records


def _text_tokenizer(processor_or_tokenizer: Any) -> Any:
    tokenizer = getattr(processor_or_tokenizer, "tokenizer", processor_or_tokenizer)
    if getattr(tokenizer, "chat_template", None) is None:
        template = getattr(processor_or_tokenizer, "chat_template", None)
        if template is not None:
            tokenizer.chat_template = template
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


class RecordDataset:
    def __init__(self, records: list[dict[str, Any]]):
        self.records = records

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.records[index]


def main() -> None:
    parser = argparse.ArgumentParser(description="Two-step NajdiLab loss-mask smoke test")
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-length", type=int, default=2048)
    args = parser.parse_args()

    seed = 42
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    if args.output_dir.exists():
        raise SystemExit(f"Refusing to overwrite an existing smoke directory: {args.output_dir}")

    model, processor_or_tokenizer = FastModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.max_length,
        load_in_4bit=True,
        load_in_8bit=False,
        full_finetuning=False,
    )
    tokenizer = _text_tokenizer(processor_or_tokenizer)
    records = load_masked_sft_records(args.export_dir, tokenizer, args.max_length)
    if len(records) != 40:
        raise SystemExit(f"Expected exactly 40 validated records, found {len(records)}")

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
        random_state=seed,
        use_gradient_checkpointing="unsloth",
    )
    model.config.use_cache = False

    training_args = TrainingArguments(
        output_dir=str(args.output_dir),
        max_steps=2,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=1,
        learning_rate=2e-5,
        warmup_steps=0,
        logging_steps=1,
        save_strategy="no",
        bf16=torch.cuda.is_bf16_supported(),
        fp16=not torch.cuda.is_bf16_supported(),
        optim="adamw_8bit",
        seed=seed,
        data_seed=seed,
        remove_unused_columns=False,
        report_to="none",
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=RecordDataset(records),
        data_collator=MaskedSFTDataCollator(tokenizer),
    )

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    trainer.train()
    duration_seconds = time.perf_counter() - started

    losses = [
        float(entry["loss"])
        for entry in trainer.state.log_history
        if "loss" in entry
    ]
    if len(losses) != 2:
        raise RuntimeError(f"Expected two logged losses, found {len(losses)}: {losses}")
    has_nan_or_inf = any(not math.isfinite(loss) for loss in losses)
    if has_nan_or_inf:
        raise RuntimeError(f"Smoke test produced NaN/Inf loss: {losses}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    adapter_saved = (args.output_dir / "adapter_model.safetensors").is_file()
    if not adapter_saved:
        raise RuntimeError("Smoke test completed but adapter_model.safetensors was not saved")

    result = {
        "records": len(records),
        "max_steps": 2,
        "seed": seed,
        "loss_step_1": losses[0],
        "loss_step_2": losses[1],
        "has_nan_or_inf": has_nan_or_inf,
        "peak_vram_allocated_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 1),
        "peak_vram_reserved_mib": round(torch.cuda.max_memory_reserved() / 1024**2, 1),
        "duration_seconds": round(duration_seconds, 2),
        "adapter_saved": adapter_saved,
        "output_dir": str(args.output_dir),
    }
    (args.output_dir / "smoke_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
