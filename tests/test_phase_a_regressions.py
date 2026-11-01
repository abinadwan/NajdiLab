"""Phase A regression tests — SEC-03/04/05, DATA-01/02/03/04/05, DB-01/02/03."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from app.db import MIGRATIONS_DIR, apply_migrations, backup_db, connect
from app.review_lifecycle import LifecycleError, append_event
from app.service import (
    ValidationError,
    bulk_update_manual_data,
    save_review,
    update_manual_data,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    apply_migrations(db)
    return db


def _insert_sft(conn: sqlite3.Connection, text: str = "مثال") -> int:
    cursor = conn.execute(
        "INSERT INTO manual_sft_items(messages_json, language_layer, origin, created_at, updated_at, version_number)"
        " VALUES(?, 'saudi_neutral', 'manual', 'now', 'now', 1)",
        (json.dumps([{"role": "user", "content": text}, {"role": "assistant", "content": text}]),),
    )
    return cursor.lastrowid


def _insert_review(conn: sqlite3.Connection, status: str = "APPROVED") -> int:
    conn.execute(
        "INSERT INTO conversations(external_conversation_id,title,source,channel,created_at,updated_at)"
        " VALUES('c1','t','test','test','now','now')"
    )
    conv_id = conn.execute("SELECT id FROM conversations WHERE external_conversation_id='c1'").fetchone()[0]
    msg_id = conn.execute(
        "INSERT INTO messages(conversation_id,turn_index,role,content,created_at)"
        " VALUES(?,0,'assistant','الرد','now')",
        (conv_id,),
    ).lastrowid
    # IGNORED/DELETED require training_eligible=0; DELETED also requires deleted_at
    eligible = 0 if status in ("IGNORED", "DELETED") else 1
    deleted_at = "now" if status == "DELETED" else None
    ignored_at = "now" if status == "IGNORED" else None
    return conn.execute(
        "INSERT INTO reviews(message_id,review_status,original_response,reviewer,"
        "training_eligible,evaluation_only,deleted_at,ignored_at,created_at,updated_at)"
        " VALUES(?,?,'الرد','human',?,0,?,?,'now','now')",
        (msg_id, status, eligible, deleted_at, ignored_at),
    ).lastrowid


# ---------------------------------------------------------------------------
# DB-01: apply_migrations ignores non-numbered SQL files
# ---------------------------------------------------------------------------

def test_db01_rollback_files_are_skipped(tmp_path):
    rollback = MIGRATIONS_DIR / "rollback_001.sql"
    helper = MIGRATIONS_DIR / "helper.sql"
    created = []
    try:
        rollback.write_text("CREATE TABLE should_not_exist (id INTEGER);", encoding="utf-8")
        helper.write_text("CREATE TABLE also_should_not_exist (id INTEGER);", encoding="utf-8")
        created = [rollback, helper]
        db = _fresh_db(tmp_path)
        conn = connect(db)
        try:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        assert "should_not_exist" not in tables
        assert "also_should_not_exist" not in tables
    finally:
        for f in created:
            f.unlink(missing_ok=True)


def test_db01_only_numbered_migrations_are_applied(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    finally:
        conn.close()
    for name in applied:
        assert re.fullmatch(r"\d{3}_[a-z0-9_]+\.sql", name), f"non-standard name in ledger: {name}"


# ---------------------------------------------------------------------------
# DB-02: migration + ledger are atomic
# ---------------------------------------------------------------------------

def test_db02_schema_migrations_count_matches_applied_files(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    finally:
        conn.close()
    numbered = [f for f in MIGRATIONS_DIR.glob("*.sql") if re.fullmatch(r"\d{3}_[a-z0-9_]+\.sql", f.name)]
    assert count == len(numbered), "ledger count does not match numbered migration files"


def test_db02_replay_is_idempotent(tmp_path):
    db = _fresh_db(tmp_path)
    apply_migrations(db)
    conn = connect(db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    finally:
        conn.close()
    numbered = [f for f in MIGRATIONS_DIR.glob("*.sql") if re.fullmatch(r"\d{3}_[a-z0-9_]+\.sql", f.name)]
    assert count == len(numbered)


# ---------------------------------------------------------------------------
# SEC-03: validate_transition called before UPDATE in _save_review_conn
# ---------------------------------------------------------------------------

def test_sec03_deleted_review_cannot_be_approved_directly(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        review_id = _insert_review(conn, status="DELETED")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValidationError, match="transition DELETED -> APPROVED is not allowed"):
        save_review(review_id, {"review_status": "APPROVED", "expected_updated_at": "now"}, db)


def test_sec03_pending_review_can_be_approved(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        review_id = _insert_review(conn, status="PENDING")
        conn.commit()
    finally:
        conn.close()
    result = save_review(review_id, {
        "review_status": "APPROVED",
        "expected_updated_at": "now",
        "reviewer": "human",
    }, db)
    assert result["review_status"] == "APPROVED"


# ---------------------------------------------------------------------------
# SEC-04: bulk_update_manual_data is atomic
# ---------------------------------------------------------------------------

def test_sec04_bulk_update_rolls_back_on_partial_failure(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        id1 = _insert_sft(conn, "أول")
        conn.commit()
    finally:
        conn.close()

    # item 2 references a non-existent id — should cause the whole batch to roll back
    with pytest.raises(ValidationError):
        bulk_update_manual_data({
            "action": "eligible",
            "items": [
                {"type": "sft", "id": id1},
                {"type": "sft", "id": 99999},
            ],
        }, db)

    # id1 must not have been updated (transaction rolled back)
    conn = connect(db)
    try:
        row = conn.execute("SELECT training_eligible FROM manual_sft_items WHERE id=?", (id1,)).fetchone()
    finally:
        conn.close()
    assert row["training_eligible"] == 0, "id1 must retain original value (0) after rollback"


# ---------------------------------------------------------------------------
# SEC-05: review_events table exists after migration
# ---------------------------------------------------------------------------

def test_sec05_review_events_table_exists_after_migration(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='review_events'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "review_events table must exist after apply_migrations"


def test_sec05_review_events_are_immutable(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        review_id = _insert_review(conn)
        conn.commit()
        append_event(conn, review_id=review_id, from_status="PENDING", to_status="APPROVED",
                     actor="tester", original_response="الرد")
        event_id = conn.execute("SELECT id FROM review_events WHERE review_id=?", (review_id,)).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE review_events SET actor='hacker' WHERE id=?", (event_id,))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM review_events WHERE id=?", (event_id,))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# DATA-01: freeze rejects zero-training-record versions
# ---------------------------------------------------------------------------

def test_data01_freeze_rejects_empty_version(tmp_path):
    from app.dataset_platform import DatasetPlatformError, freeze_dataset_version
    import os

    exports = tmp_path / "exports"
    version_dir = exports / "gold-test-v001"
    version_dir.mkdir(parents=True)
    (version_dir / "manifest.json").write_text(
        json.dumps({"version": "gold-test-v001", "state": "Draft", "sha256": {}}),
        encoding="utf-8",
    )

    import app.dataset_platform as dp
    original_exports = dp.EXPORTS_DIR
    dp.EXPORTS_DIR = str(exports)
    try:
        with pytest.raises(DatasetPlatformError, match="no training records"):
            freeze_dataset_version("gold-test-v001")
    finally:
        dp.EXPORTS_DIR = original_exports


# ---------------------------------------------------------------------------
# DATA-02: _diagnostics_status gives actionable messages
# ---------------------------------------------------------------------------

def test_data02_missing_diagnostics_message_is_actionable():
    from app.dataset_platform import _diagnostics_status
    from pathlib import Path

    directory = Path("/nonexistent-for-test")
    manifest_no_diag: dict = {"version": "gold-test-v001"}
    ok, msg = _diagnostics_status(directory, manifest_no_diag)
    assert not ok
    assert "not been generated" in (msg or ""), f"expected actionable message, got: {msg!r}"


def test_data02_stale_diagnostics_message_is_distinct():
    from app.dataset_platform import _diagnostics_status
    from pathlib import Path

    directory = Path("/nonexistent-for-test")
    manifest_stale: dict = {
        "version": "gold-test-v001",
        "diagnostics": {"version": "gold-test-DIFFERENT", "training_fingerprint": "abc", "artifacts": {}},
    }
    ok, msg = _diagnostics_status(directory, manifest_stale)
    assert not ok
    assert "stale" in (msg or ""), f"expected stale message, got: {msg!r}"


# ---------------------------------------------------------------------------
# DATA-03 / DATA-04: evaluation_holdout.jsonl is in DATASET_FILES
# ---------------------------------------------------------------------------

def test_data03_evaluation_holdout_in_dataset_files():
    from app.dataset_balancer import DATASET_FILES
    assert "evaluation_holdout.jsonl" in DATASET_FILES, (
        "evaluation_holdout.jsonl must be in DATASET_FILES"
    )
    assert DATASET_FILES["evaluation_holdout.jsonl"] == "evaluation"


def test_data04_eval_files_single_source_of_truth():
    from app.dataset_balancer import DATASET_FILES
    from app.dataset_platform import EVAL_FILES
    for name in EVAL_FILES:
        assert name in DATASET_FILES, (
            f"{name} is in dataset_platform.EVAL_FILES but missing from dataset_balancer.DATASET_FILES"
        )


# ---------------------------------------------------------------------------
# DATA-05: _exports_root creates directory instead of raising
# ---------------------------------------------------------------------------

def test_data05_missing_exports_root_is_created(tmp_path, monkeypatch):
    import app.dataset_platform as dp
    missing = str(tmp_path / "nonexistent" / "exports")
    monkeypatch.setattr(dp, "EXPORTS_DIR", missing)
    root = dp._exports_root()
    assert root.is_dir(), "_exports_root must create the directory if missing"


# ---------------------------------------------------------------------------
# DB-03: backup produces a consistent, recoverable copy
# ---------------------------------------------------------------------------

def test_db03_backup_produces_consistent_copy(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        conn.execute(
            "INSERT INTO conversations(external_conversation_id,title,source,channel,created_at,updated_at)"
            " VALUES('bk1','t','test','test','now','now')"
        )
        conn.commit()
    finally:
        conn.close()

    dest = tmp_path / "backup.db"
    result = backup_db(db, dest)
    assert result == dest
    assert dest.is_file()

    bk_conn = connect(dest)
    try:
        row = bk_conn.execute(
            "SELECT external_conversation_id FROM conversations WHERE external_conversation_id='bk1'"
        ).fetchone()
        migrations = bk_conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    finally:
        bk_conn.close()
    assert row is not None, "backup must contain committed rows"
    assert migrations > 0, "backup must include schema_migrations table"


def test_db03_recovery_from_backup_is_idempotent(tmp_path):
    db = _fresh_db(tmp_path)
    dest = backup_db(db, tmp_path / "recovery.db")
    # Recovery: restore file and re-run apply_migrations — must be a no-op
    apply_migrations(dest)
    conn = connect(dest)
    try:
        numbered = [f for f in MIGRATIONS_DIR.glob("*.sql") if re.fullmatch(r"\d{3}_[a-z0-9_]+\.sql", f.name)]
        count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    finally:
        conn.close()
    assert count == len(numbered), "recovery + replay must not duplicate ledger entries"
