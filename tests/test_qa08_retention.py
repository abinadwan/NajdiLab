"""QA-08: end-to-end retention and deletion semantics.

The tests record what NajdiLab actually does, so the documentation can state it without
guessing. In short: exclusion and deletion take a record out of training selection and
out of new training files; nothing is physically erased. The database, audit history,
earlier exports, the full archive of every new export, and backups keep the content.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.db import apply_migrations, backup_db, connect
from app.service import (
    ValidationError,
    add_direct_text,
    create_export,
    delete_manual_data,
    delete_review,
    exclude_review,
    ignore_manual_data,
    ingest_turn,
    restore_review,
    save_review,
    training_dataset,
)

PRIVATE = "نص اصطناعي يمثل محتوى يطلب صاحبه حذفه"


@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "retention.db"
    apply_migrations(path)
    return path


def _turn(db: Path, key: str, assistant: str) -> int:
    result = ingest_turn({"conversation_id": key, "title": "اختبار الاحتفاظ", "source": "api", "channel": "web",
                          "provider": "local", "model_name": "synthetic", "user_message": "سؤال", "assistant_response": assistant}, db)
    return result["review_id"]


def _selected_review_ids(db: Path) -> set[int]:
    # Training selection identifies reviews as "review:<id>".
    return {int(str(item["id"]).split(":", 1)[1]) for item in training_dataset(db)["reviews"]}


def _row(db: Path, review_id: int) -> sqlite3.Row:
    conn = connect(db)
    try:
        return conn.execute("SELECT r.*, m.content FROM reviews r JOIN messages m ON m.id=r.message_id WHERE r.id=?",
                            (review_id,)).fetchone()
    finally:
        conn.close()


def _events(db: Path, review_id: int) -> list[str]:
    conn = connect(db)
    try:
        return [r[0] for r in conn.execute("SELECT to_status FROM review_events WHERE review_id=? ORDER BY sequence", (review_id,))]
    finally:
        conn.close()


def test_review_exclusion_restoration_and_deletion_change_selection_but_erase_nothing(db, tmp_path):
    review_id = _turn(db, "retention-review", PRIVATE)
    save_review(review_id, {"review_status": "APPROVED", "reviewer": "human", "training_eligible": True}, db)
    assert review_id in _selected_review_ids(db)

    exclude_review(review_id, {"reason": "synthetic exclusion", "reviewer": "human"}, db)
    assert review_id not in _selected_review_ids(db), "excluded reviews leave training selection"

    restore_review(review_id, {"reason": "synthetic restoration", "reviewer": "human"}, db)
    row = _row(db, review_id)
    assert row["review_status"] == "PENDING" and row["training_eligible"] == 0
    assert review_id not in _selected_review_ids(db), "restoration needs a new human decision"

    delete_review(review_id, {"reason": "synthetic deletion", "reviewer": "human"}, db)
    row = _row(db, review_id)
    assert row["review_status"] == "DELETED" and row["deleted_at"]
    assert row["content"] == PRIVATE and row["original_response"] == PRIVATE, "soft deletion keeps the text"
    assert review_id not in _selected_review_ids(db)
    assert _events(db, review_id) == ["APPROVED", "IGNORED", "PENDING", "DELETED"], "audit history is kept"

    conn = connect(db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM reviews WHERE id=?", (review_id,))
    finally:
        conn.close()

    copy = backup_db(db, tmp_path / "after-delete.db")
    conn = connect(copy)
    try:
        assert conn.execute("SELECT deleted_at IS NOT NULL FROM reviews WHERE id=?", (review_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM messages WHERE content=?", (PRIVATE,)).fetchone()[0] == 1
    finally:
        conn.close()


def test_deleted_review_text_stays_in_every_new_full_archive_but_not_in_training_files(db, tmp_path):
    deleted = _turn(db, "retention-deleted", PRIVATE)
    kept = _turn(db, "retention-kept", "رد معتمد اصطناعي")
    delete_review(deleted, {"reason": "synthetic deletion", "reviewer": "human"}, db)
    save_review(kept, {"review_status": "APPROVED", "reviewer": "human", "training_eligible": True}, db)
    export = Path(create_export(db, tmp_path / "exports")["path"])
    training = "".join(p.read_text(encoding="utf-8") for p in export.glob("*.jsonl"))
    assert PRIVATE not in training, "deleted text never enters training files"
    archive = json.loads((export / "full_archive.json").read_text(encoding="utf-8"))
    archived = {item["id"]: item for item in archive["reviews"]}
    assert archived[deleted]["review_status"] == "DELETED"
    assert PRIVATE in json.dumps(archive, ensure_ascii=False), "the full archive keeps deleted text"


def test_manual_record_ignore_and_delete_leave_earlier_exports_and_history_intact(db, tmp_path):
    item = add_direct_text({"text": PRIVATE, "language_layer": "msa", "source_type": "human_written", "origin": "manual",
                            "training_eligible": True}, db)
    first = Path(create_export(db, tmp_path / "exports")["path"])
    exported = (first / "direct_language.jsonl").read_text(encoding="utf-8")
    assert PRIVATE in exported

    ignore_manual_data("direct", item["id"], {"reason": "synthetic ignore"}, db)
    assert not any(row["id"] == item["id"] for row in training_dataset(db)["direct_language"])
    with pytest.raises(ValidationError):
        delete_manual_data("direct", item["id"], False, db)
    delete_manual_data("direct", item["id"], True, db)

    assert (first / "direct_language.jsonl").read_text(encoding="utf-8") == exported, "frozen exports are never rewritten"
    conn = connect(db)
    try:
        stored = conn.execute("SELECT text, deleted_at FROM direct_language_texts WHERE id=?", (item["id"],)).fetchone()
        versions = conn.execute("SELECT COUNT(*) FROM manual_data_versions WHERE item_type='direct' AND item_id=?",
                                (item["id"],)).fetchone()[0]
    finally:
        conn.close()
    assert stored["text"] == PRIVATE and stored["deleted_at"], "manual deletion is soft"
    assert versions >= 1, "version snapshots are kept"

    add_direct_text({"text": "نص آخر مؤهل", "language_layer": "msa", "source_type": "human_written", "origin": "manual",
                     "training_eligible": True}, db)
    second = Path(create_export(db, tmp_path / "exports")["path"])
    assert PRIVATE not in (second / "direct_language.jsonl").read_text(encoding="utf-8")
    archive = json.loads((second / "full_archive.json").read_text(encoding="utf-8"))
    deleted = [row for row in archive["direct_language_texts"] if row["id"] == item["id"]]
    assert deleted and deleted[0]["text"] == PRIVATE and deleted[0]["deleted_at"], "the full archive keeps deleted manual text"
