"""Synthetic dataset versions for browser fixtures; never real or private data."""
from __future__ import annotations

import json
from pathlib import Path

SOURCE = "gold-v001-synthetic"
DRAFT = "gold-v002-synthetic-draft"


def _row(record_id: str, conversation: str, target: str, turns: int = 1) -> dict:
    messages = []
    for index in range(turns):
        messages += [{"role": "user", "content": f"سؤال اصطناعي {index}"},
                     {"role": "assistant", "content": target if index == turns - 1 else f"رد اصطناعي {index}"}]
    last = len(messages) - 1
    return {"id": record_id, "conversation_id": conversation, "messages": messages,
            "target_message_index": last, "message_loss_mask": [0] * last + [1]}


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def attach_synthetic_catalog(platform, root: Path) -> Path:
    """Bind an existing fixture catalog without changing its Frozen seed files."""
    exports = root / "exports"
    platform.EXPORTS_ROOT = platform.EXPORTS_DIR = exports
    platform.DATASETS_ROOT = root / "datasets"
    return exports


def bind_synthetic_catalog(platform, root: Path) -> Path:
    """Point the dataset platform at a temporary catalog with one source and one derived Draft."""
    exports = root / "exports"
    source = exports / SOURCE
    source.mkdir(parents=True)
    _write(source / "sft.jsonl", [_row(f"s{i}", f"c{i}", f"هدف اصطناعي {i}") for i in range(4)])
    _write(source / "multi_turn.jsonl", [_row(f"m{i}", f"mc{i}", f"هدف متعدد {i}", 2) for i in range(4)])
    _write(source / "text_sft_eval.jsonl", [_row("e1", "eval-c1", "هدف تقييم اصطناعي")])
    (source / "manifest.json").write_text(json.dumps({
        "version": SOURCE, "created_at": "2026-01-01T00:00:00Z", "source_version": "synthetic",
        "files": {"sft.jsonl": 4, "multi_turn.jsonl": 4, "text_sft_eval.jsonl": 1},
        "loss_mask_validation": {"passed": 8, "total": 8, "failures": []},
    }), encoding="utf-8")
    attach_synthetic_catalog(platform, root)
    platform.create_derived_version(SOURCE, DRAFT)
    return exports
