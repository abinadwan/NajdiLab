from __future__ import annotations

# Retained for historical validation imports, retired as an executable.
if __name__ == '__main__':
    raise SystemExit('Training is retired in NajdiLab. Export a reviewed dataset for external Unsloth.')


import argparse
import gc
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from transformers import Trainer, TrainingArguments

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_gold_v006_controlled as v006
from scripts.train_najdi_sft import MaskedSFTDataCollator, load_masked_sft_records


SEED = 42
EXPECTED_RECORDS = 33
SMOKE_STEPS = 2


class RecordDataset:
    def __init__(self, records: list[dict[str, Any]]):
        self.records = records

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.records[index]


def seed_everything() -> None:
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)


def smoke(export_dir: Path, model_path: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise SystemExit(f"Refusing to overwrite existing smoke output: {output_dir}")
    seed_everything()
    model, processor_or_tokenizer = v006.FastModel.from_pretrained(
        model_name=str(model_path),
        max_seq_length=v006.TRAIN_MAX_LENGTH,
        load_in_4bit=True,
        load_in_8bit=False,
        full_finetuning=False,
    )
    _, tokenizer = v006.processor_and_tokenizer(processor_or_tokenizer)
    records = load_masked_sft_records(export_dir, tokenizer, v006.TRAIN_MAX_LENGTH)
    if len(records) != EXPECTED_RECORDS:
        raise SystemExit(f"Expected {EXPECTED_RECORDS} validated records, found {len(records)}")
    model = v006.FastModel.get_peft_model(
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
        max_steps=SMOKE_STEPS,
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
    )
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    trainer.train()
    elapsed = time.perf_counter() - started
    losses = [float(entry["loss"]) for entry in trainer.state.log_history if "loss" in entry]
    if len(losses) != SMOKE_STEPS:
        raise RuntimeError(f"Expected {SMOKE_STEPS} logged losses, got {losses}")
    if any(not math.isfinite(loss) for loss in losses):
        raise RuntimeError(f"Smoke produced NaN/Inf: {losses}")
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    adapter_saved = (output_dir / "adapter_model.safetensors").is_file()
    if not adapter_saved:
        raise RuntimeError("Smoke completed without saving adapter_model.safetensors")
    result = {
        "records": EXPECTED_RECORDS,
        "max_steps": SMOKE_STEPS,
        "optimizer_steps": trainer.state.global_step,
        "seed": SEED,
        "loss_step_1": losses[0],
        "loss_step_2": losses[1],
        "has_nan_or_inf": False,
        "peak_vram_allocated_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 1),
        "peak_vram_reserved_mib": round(torch.cuda.max_memory_reserved() / 1024**2, 1),
        "duration_seconds": round(elapsed, 2),
        "adapter_saved": adapter_saved,
        "output_dir": str(output_dir),
    }
    (output_dir / "smoke_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    del model
    gc.collect()
    torch.cuda.empty_cache()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def train(export_dir: Path, model_path: Path, output_dir: Path) -> None:
    if output_dir.exists():
        raise SystemExit(f"Refusing to overwrite existing training output: {output_dir}")
    # Reuse v006's exact controlled training implementation and settings;
    # only the expected v007 dataset counts are changed at runtime.
    v006.EXPECTED_MULTI = 17
    v006.EXPECTED_TRAIN = 33
    v006.train(export_dir, model_path, output_dir)


def benchmark(export_dir: Path, model_path: Path, adapter: Path | None, label: str, output: Path) -> None:
    v006.benchmark(export_dir, model_path, output, label, adapter)


def main() -> None:
    parser = argparse.ArgumentParser(description="Controlled gold-v007-balanced smoke, training, and benchmark")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("smoke", "train"):
        item = sub.add_parser(command)
        item.add_argument("--export-dir", type=Path, required=True)
        item.add_argument("--model", type=Path, required=True)
        item.add_argument("--output-dir", type=Path, required=True)
    item = sub.add_parser("benchmark")
    item.add_argument("--export-dir", type=Path, required=True)
    item.add_argument("--model", type=Path, required=True)
    item.add_argument("--adapter", type=Path)
    item.add_argument("--label", required=True)
    item.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "smoke":
        smoke(args.export_dir, args.model, args.output_dir)
    elif args.command == "train":
        train(args.export_dir, args.model, args.output_dir)
    else:
        benchmark(args.export_dir, args.model, args.adapter, args.label, args.output)


if __name__ == "__main__":
    main()
