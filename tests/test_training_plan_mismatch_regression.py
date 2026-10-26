"""Production train-plan regression tests with a fully mocked training stack."""

from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import najdilab_training_adapter as adapter


class _Tokenizer:
    chat_template = "{{ messages }}"
    bos_token_id = 1
    eos_token_id = 2
    pad_token_id = 0
    unk_token_id = 3

    def save_pretrained(self, path):
        Path(path, "tokenizer.json").write_text("{}", encoding="utf-8")


class _Model:
    def save_pretrained(self, path):
        Path(path, "adapter.json").write_text("{}", encoding="utf-8")


def _arguments(tmp_path: Path, *, smoke: bool, expected_steps: int = 27) -> argparse.Namespace:
    return argparse.Namespace(
        model_path=tmp_path / "model", output_dir=tmp_path / "output",
        checkpoint_dir=tmp_path / "checkpoints", logs_dir=tmp_path / "logs",
        sft_file=tmp_path / "data" / "sft.jsonl", native_tool_file=None,
        capability_registry=None, max_seq_length=2048, lora_r=16, lora_alpha=32,
        lora_dropout=0.0, seed=3407, gradient_checkpointing=True,
        full_training=not smoke, smoke_test=smoke, max_steps=2 if smoke else 27,
        expected_steps=expected_steps, epochs=1.0, batch_size=4,
        gradient_accumulation_steps=1, learning_rate=2e-4, warmup_ratio=0.03,
        weight_decay=0.01, lr_scheduler="cosine", save_steps=0, bf16=True,
        fp16=False, optimizer="adamw_8bit",
    )


def _install_fake_training_stack(monkeypatch, *, completed_steps: int):
    observed = {"training_arguments": None, "train_calls": 0}

    class FakeCuda:
        is_available = staticmethod(lambda: True)
        memory_allocated = staticmethod(lambda: 0)
        memory_reserved = staticmethod(lambda: 0)
        max_memory_allocated = staticmethod(lambda: 0)
        max_memory_reserved = staticmethod(lambda: 0)
        reset_peak_memory_stats = staticmethod(lambda: None)

    torch = types.ModuleType("torch")
    torch.cuda = FakeCuda()

    class TrainingArguments:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            observed["training_arguments"] = kwargs

    class TrainerCallback:
        pass

    class Trainer:
        def __init__(self, *, args, callbacks, **kwargs):
            self.args = args
            self.callbacks = callbacks
            self.state = types.SimpleNamespace(global_step=0, max_steps=args.max_steps, epoch=0.0)

        def train(self):
            observed["train_calls"] += 1
            self.state.global_step = completed_steps
            self.state.epoch = completed_steps / 27
            for callback in self.callbacks:
                callback.on_log(None, self.state, None, {"loss": 1.0, "learning_rate": 2e-4})
            return types.SimpleNamespace(metrics={"train_loss": 1.0})

    transformers = types.ModuleType("transformers")
    transformers.Trainer = Trainer
    transformers.TrainingArguments = TrainingArguments
    transformers.TrainerCallback = TrainerCallback

    class FastModel:
        from_pretrained = staticmethod(lambda **kwargs: (_Model(), _Tokenizer()))
        get_peft_model = staticmethod(lambda model, **kwargs: model)

    unsloth = types.ModuleType("unsloth")
    unsloth.FastModel = FastModel
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    monkeypatch.setitem(sys.modules, "unsloth", unsloth)
    monkeypatch.setattr(adapter, "load_masked_training_records", lambda *args, **kwargs: [{}] * 108)
    monkeypatch.setattr(adapter, "MaskedSFTDataCollator", lambda tokenizer: object())
    return observed


def _run(tmp_path, monkeypatch, *, smoke: bool, completed_steps: int, expected_steps: int = 27):
    observed = _install_fake_training_stack(monkeypatch, completed_steps=completed_steps)
    result = adapter.train(
        _arguments(tmp_path, smoke=smoke, expected_steps=expected_steps),
        {"training_records": 108},
    )
    return result, observed


def test_smoke_validates_full_27_step_plan_but_executes_exactly_two(tmp_path, monkeypatch):
    result, observed = _run(tmp_path, monkeypatch, smoke=True, completed_steps=2)
    assert observed["training_arguments"]["max_steps"] == 2
    assert observed["train_calls"] == 1
    assert result["global_step"] == result["expected_steps"] == 2


def test_full_training_validates_and_executes_expected_27_steps(tmp_path, monkeypatch):
    result, observed = _run(tmp_path, monkeypatch, smoke=False, completed_steps=27)
    assert observed["training_arguments"]["max_steps"] == 27
    assert observed["train_calls"] == 1
    assert result["global_step"] == result["expected_steps"] == 27


@pytest.mark.parametrize("smoke", [True, False])
def test_genuine_full_plan_mismatch_is_rejected_before_trainer_train(tmp_path, monkeypatch, smoke):
    observed = _install_fake_training_stack(monkeypatch, completed_steps=2)
    with pytest.raises(RuntimeError, match="TRAINING_PLAN_MISMATCH"):
        adapter.train(_arguments(tmp_path, smoke=smoke, expected_steps=26), {"training_records": 108})
    assert observed["train_calls"] == 0


@pytest.mark.parametrize("completed_steps", [1, 3])
def test_smoke_rejects_completed_optimizer_step_count_other_than_two(
    tmp_path, monkeypatch, completed_steps
):
    with pytest.raises(RuntimeError, match="training success criteria failed"):
        _run(tmp_path, monkeypatch, smoke=True, completed_steps=completed_steps)
