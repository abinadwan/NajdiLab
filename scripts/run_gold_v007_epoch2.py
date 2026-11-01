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
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from scripts import run_gold_v006_controlled as v006
from scripts.train_najdi_sft import MaskedSFTDataCollator, load_masked_sft_records


SEED = 42
SFT_COUNT = 16
MULTI_COUNT = 17
TRAIN_COUNT = 33
EPOCHS = 2
EXPECTED_STEPS = TRAIN_COUNT * EPOCHS
MODEL_PATH = Path("/home/najdi/najdi-training/models/Ministral-3-3B-Instruct-2512-unsloth-bnb-4bit")
E1_PATH = Path("/home/najdi/najdi-training/checkpoints/najdilab-gold-v007-balanced-epoch1")


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


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def preflight(export_dir: Path, model_path: Path, output_dir: Path) -> dict[str, Any]:
    sft = read_jsonl(export_dir / "sft.jsonl")
    multi = read_jsonl(export_dir / "multi_turn.jsonl")
    evaluation = read_jsonl(export_dir / "text_sft_eval.jsonl")
    if len(sft) != SFT_COUNT or len(multi) != MULTI_COUNT or len(sft) + len(multi) != TRAIN_COUNT:
        raise RuntimeError(f"dataset count mismatch: sft={len(sft)}, multi={len(multi)}")
    if not model_path.exists():
        raise RuntimeError(f"base model missing: {model_path}")
    if not E1_PATH.joinpath("adapter_model.safetensors").is_file():
        raise RuntimeError(f"v007 E1 adapter missing: {E1_PATH}")
    if output_dir.exists():
        raise RuntimeError(f"epoch2 output already exists; refusing overwrite: {output_dir}")
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("GPU/BF16 preflight failed")
    train_conv = {str(row.get("conversation_id")) for row in sft + multi if row.get("conversation_id") is not None}
    eval_conv = {str(row.get("conversation_id")) for row in evaluation if row.get("conversation_id") is not None}
    if train_conv & eval_conv:
        raise RuntimeError(f"train/eval conversation leakage: {sorted(train_conv & eval_conv)}")
    train_targets = {row["messages"][row["target_message_index"]]["content"] for row in sft + multi}
    eval_targets = {row["messages"][row["target_message_index"]]["content"] for row in evaluation}
    if train_targets & eval_targets:
        raise RuntimeError("train/eval exact target leakage")
    return {
        "dataset_sft": len(sft),
        "dataset_multi_turn": len(multi),
        "dataset_total": len(sft) + len(multi),
        "evaluation_total": len(evaluation),
        "base_model": str(model_path),
        "base_model_matches_e1": str(model_path) == str(MODEL_PATH),
        "v007_e1_present": True,
        "output_path_new": True,
        "gpu_ready": True,
        "bf16_ready": True,
        "train_eval_conversation_overlap": 0,
        "train_eval_exact_target_overlap": 0,
    }


def train(export_dir: Path, model_path: Path, output_dir: Path) -> dict[str, Any]:
    preflight_result = preflight(export_dir, model_path, output_dir)
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
    if len(records) != TRAIN_COUNT:
        raise RuntimeError(f"loss-mask/tokenizer validation did not yield {TRAIN_COUNT} records")
    preflight_result["loss_mask_records_loaded"] = len(records)
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
        num_train_epochs=EPOCHS,
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
        callbacks=[v006.StopOnInvalidLoss()],
    )
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    train_result = trainer.train()
    duration = time.perf_counter() - started
    loss_history = [
        {"step": int(entry["step"]), "loss": float(entry["loss"]), "learning_rate": float(entry["learning_rate"]), "epoch": float(entry["epoch"])}
        for entry in trainer.state.log_history if "loss" in entry
    ]
    losses = [entry["loss"] for entry in loss_history]
    if trainer.state.global_step != EXPECTED_STEPS or len(loss_history) != EXPECTED_STEPS:
        raise RuntimeError(f"expected {EXPECTED_STEPS} steps/losses, got {trainer.state.global_step}/{len(loss_history)}")
    if any(not math.isfinite(loss) for loss in losses):
        raise RuntimeError("NaN/Inf loss detected; adapter will not be saved")
    epoch1_end = next(entry["loss"] for entry in loss_history if entry["step"] == TRAIN_COUNT)
    epoch2_end = next(entry["loss"] for entry in loss_history if entry["step"] == EXPECTED_STEPS)
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    if not (output_dir / "adapter_model.safetensors").is_file():
        raise RuntimeError("adapter was not saved")
    peft_config = next(iter(model.peft_config.values()))
    metrics = {
        "preflight": preflight_result,
        "dataset": "gold-v007-balanced",
        "base_model": str(model_path),
        "epochs": EPOCHS,
        "optimizer_steps": int(trainer.state.global_step),
        "seed": SEED,
        "learning_rate": 2e-5,
        "scheduler": "linear",
        "batch_size": 1,
        "gradient_accumulation": 1,
        "effective_batch_size": 1,
        "precision": "bf16",
        "optimizer": "adamw_8bit",
        "max_training_length": 2048,
        "load_in_4bit": True,
        "lora": {"r": int(peft_config.r), "alpha": int(peft_config.lora_alpha), "dropout": float(peft_config.lora_dropout), "bias": str(peft_config.bias), "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"], "vision": "frozen", "language": "trainable", "gradient_checkpointing": "unsloth"},
        "first_loss": losses[0],
        "epoch1_end_loss": epoch1_end,
        "epoch2_end_loss": epoch2_end,
        "last_loss": losses[-1],
        "mean_loss": sum(losses) / len(losses),
        "min_loss": min(losses),
        "max_loss": max(losses),
        "has_nan_or_inf": False,
        "duration_seconds": round(duration, 2),
        "peak_vram_allocated_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 1),
        "peak_vram_reserved_mib": round(torch.cuda.max_memory_reserved() / 1024**2, 1),
        "adapter_path": str(output_dir),
        "adapter_saved": True,
        "resumed_from_epoch1": False,
        "trainer_metrics": {key: float(value) for key, value in train_result.metrics.items()},
    }
    (output_dir / "loss_history.jsonl").write_text("\n".join(json.dumps(entry) for entry in loss_history) + "\n", encoding="utf-8")
    (output_dir / "training_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    del model
    gc.collect()
    torch.cuda.empty_cache()
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    train(args.export_dir, args.model, args.output_dir)


if __name__ == "__main__":
    main()
