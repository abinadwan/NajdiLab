"""Phase A regression tests — SEC-03/04/05, DATA-01/02/03/04/05, DB-01/02/03."""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

import app.db as db_module
from app.db import (
    MIGRATIONS_DIR,
    MigrationFormError,
    _MIGRATION_BLOCKED,
    _MIGRATION_NAME,
    apply_migrations,
    atomic_migration_script,
    backup_db,
    connect,
)
from app.review_integrity import export_readiness
from app.review_lifecycle import append_event
from app.service import (
    ValidationError,
    bulk_update_manual_data,
    delete_review,
    ignore_review,
    restore_review,
    save_review,
)

SHIPPED = sorted(
    p for p in MIGRATIONS_DIR.glob("*.sql")
    if _MIGRATION_NAME.fullmatch(p.name) and not _MIGRATION_BLOCKED.search(p.name)
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def migrations_dir(tmp_path, monkeypatch):
    """Isolated copy of the shipped migrations; tests never write into the repository."""
    target = tmp_path / "migrations"
    target.mkdir()
    for path in SHIPPED:
        shutil.copy2(path, target / path.name)
    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", target)
    return target


def _fresh_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    apply_migrations(db)
    return db


def _tables(db: Path) -> set[str]:
    conn = connect(db)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def _ledger(db: Path) -> set[str]:
    conn = connect(db)
    try:
        return {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    finally:
        conn.close()


def _insert_sft(conn: sqlite3.Connection, text: str = "مثال") -> int:
    cursor = conn.execute(
        "INSERT INTO manual_sft_items(messages_json, language_layer, origin, created_at, updated_at, version_number)"
        " VALUES(?, 'saudi_neutral', 'manual', 'now', 'now', 1)",
        (json.dumps([{"role": "user", "content": text}, {"role": "assistant", "content": text}]),),
    )
    return cursor.lastrowid


def _insert_review(conn: sqlite3.Connection, status: str = "APPROVED", key: str = "c1") -> int:
    conn.execute(
        "INSERT INTO conversations(external_conversation_id,title,source,channel,created_at,updated_at)"
        " VALUES(?,'t','test','test','now','now')", (key,),
    )
    conv_id = conn.execute("SELECT id FROM conversations WHERE external_conversation_id=?", (key,)).fetchone()[0]
    msg_id = conn.execute(
        "INSERT INTO messages(conversation_id,turn_index,role,content,created_at)"
        " VALUES(?,0,'assistant','الرد','now')",
        (conv_id,),
    ).lastrowid
    eligible = 0 if status in ("IGNORED", "DELETED", "PENDING") else 1
    deleted_at = "now" if status == "DELETED" else None
    ignored_at = "now" if status == "IGNORED" else None
    return conn.execute(
        "INSERT INTO reviews(message_id,review_status,original_response,reviewer,"
        "training_eligible,evaluation_only,deleted_at,ignored_at,created_at,updated_at)"
        " VALUES(?,?,'الرد','human',?,0,?,?,'now','now')",
        (msg_id, status, eligible, deleted_at, ignored_at),
    ).lastrowid


def _codes(result: dict) -> set[str]:
    return {item["code"] for item in result["findings"]}


# ---------------------------------------------------------------------------
# DB-01: only real forward migrations are applied
# ---------------------------------------------------------------------------

def test_db01_unnumbered_rollback_and_helper_files_are_skipped(tmp_path, migrations_dir):
    (migrations_dir / "rollback_001.sql").write_text("CREATE TABLE should_not_exist (id INTEGER);", encoding="utf-8")
    (migrations_dir / "helper.sql").write_text("CREATE TABLE also_should_not_exist (id INTEGER);", encoding="utf-8")
    db = _fresh_db(tmp_path)
    assert not {"should_not_exist", "also_should_not_exist"} & _tables(db)


@pytest.mark.parametrize("name", [
    "099_rollback.sql", "099_rollback_review_events.sql", "099_revert_schema.sql",
    "099_undo_labels.sql", "099_down.sql", "099_helper.sql", "099_seed_demo.sql", "099_fixture.sql",
])
def test_db01_numbered_rollback_like_files_are_rejected(tmp_path, migrations_dir, name):
    (migrations_dir / name).write_text("CREATE TABLE must_not_appear (id INTEGER);", encoding="utf-8")
    db = _fresh_db(tmp_path)
    assert "must_not_appear" not in _tables(db)
    assert name not in _ledger(db)


def test_db01_shipped_migrations_all_pass_and_are_all_recorded(tmp_path, migrations_dir):
    db = _fresh_db(tmp_path)
    assert _ledger(db) == {p.name for p in SHIPPED}


# ---------------------------------------------------------------------------
# DB-02: migration DDL and its ledger row commit or roll back together
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.name)
def test_db02_every_shipped_migration_is_a_supported_form(path):
    sql = path.read_text(encoding="utf-8")
    script = atomic_migration_script(path.name, sql, "2026-01-01T00:00:00Z")
    ledger_at = script.index(f"VALUES ('{path.name}'")
    commit_at = script.upper().rindex("COMMIT;")
    assert ledger_at < commit_at, "ledger row must be written inside the migration transaction"
    assert script.upper().count("COMMIT;") == 1


def test_db02_failed_wrapped_migration_leaves_no_schema_or_ledger(tmp_path, migrations_dir):
    db = _fresh_db(tmp_path)
    bad = migrations_dir / "098_bad_wrapped.sql"
    bad.write_text("CREATE TABLE partial_artifact (id INTEGER);\nNOT_VALID_SQL;\n", encoding="utf-8")
    with pytest.raises(sqlite3.Error):
        apply_migrations(db)
    assert "partial_artifact" not in _tables(db)
    assert bad.name not in _ledger(db)


def test_db02_failed_self_transacted_migration_leaves_no_schema_or_ledger(tmp_path, migrations_dir):
    db = _fresh_db(tmp_path)
    bad = migrations_dir / "098_bad_self_tx.sql"
    bad.write_text(
        "PRAGMA foreign_keys = OFF;\nBEGIN IMMEDIATE;\nCREATE TABLE partial_tx (id INTEGER);\n"
        "INSERT INTO partial_tx VALUES (1);\nNOT_VALID_SQL;\nCOMMIT;\nPRAGMA foreign_keys = ON;\n",
        encoding="utf-8",
    )
    with pytest.raises(sqlite3.Error):
        apply_migrations(db)
    assert "partial_tx" not in _tables(db)
    assert bad.name not in _ledger(db)


def test_db02_retry_after_fix_succeeds(tmp_path, migrations_dir):
    db = _fresh_db(tmp_path)
    bad = migrations_dir / "097_broken_then_fixed.sql"
    bad.write_text("NOT_VALID_SQL;\n", encoding="utf-8")
    with pytest.raises(sqlite3.Error):
        apply_migrations(db)
    bad.write_text("CREATE TABLE was_broken_now_fixed (id INTEGER);\n", encoding="utf-8")
    apply_migrations(db)
    assert "was_broken_now_fixed" in _tables(db)
    assert bad.name in _ledger(db)
    apply_migrations(db)
    assert len(_ledger(db)) == len(SHIPPED) + 1


@pytest.mark.parametrize("sql", [
    "BEGIN;\nCREATE TABLE a (id INTEGER);\nCOMMIT;\nBEGIN;\nCREATE TABLE b (id INTEGER);\nCOMMIT;\n",
    "BEGIN;\nCREATE TABLE a (id INTEGER);\nCOMMIT;\nCREATE TABLE b (id INTEGER);\n",
    "CREATE TABLE b (id INTEGER);\nBEGIN;\nCREATE TABLE a (id INTEGER);\nCOMMIT;\n",
    "BEGIN;\nCREATE TABLE a (id INTEGER);\n",
    "CREATE TABLE a (id INTEGER);\nCOMMIT;\n",
    "BEGIN;\nCREATE TABLE a (id INTEGER);\nROLLBACK;\n",
    "SAVEPOINT s;\nCREATE TABLE a (id INTEGER);\nRELEASE s;\n",
], ids=["two-pairs", "after-commit", "before-begin", "no-commit", "no-begin", "rollback", "savepoint"])
def test_db02_unsupported_forms_are_rejected_before_any_migration_runs(tmp_path, migrations_dir, sql):
    db = _fresh_db(tmp_path)
    (migrations_dir / "096_valid_but_earlier.sql").write_text("CREATE TABLE earlier (id INTEGER);\n", encoding="utf-8")
    (migrations_dir / "099_unsupported.sql").write_text(sql, encoding="utf-8")
    with pytest.raises(MigrationFormError):
        apply_migrations(db)
    tables = _tables(db)
    assert not {"a", "b", "earlier"} & tables
    assert not {"096_valid_but_earlier.sql", "099_unsupported.sql"} & _ledger(db)


def test_db02_trigger_bodies_are_not_mistaken_for_transactions():
    sql = (
        "CREATE TABLE t (id INTEGER);\n"
        "CREATE TRIGGER t_guard BEFORE DELETE ON t\nBEGIN\n    SELECT RAISE(ABORT, 'no');\nEND;\n"
        "CREATE TRIGGER t_guard2 BEFORE UPDATE ON t\nBEGIN SELECT RAISE(ABORT, 'no'); END;\n"
    )
    script = atomic_migration_script("050_triggers.sql", sql, "x")
    assert script.startswith("BEGIN IMMEDIATE;")


def test_db02_existing_installation_upgrades_to_007(tmp_path, migrations_dir):
    for path in migrations_dir.glob("007_*.sql"):
        path.unlink()
    db = _fresh_db(tmp_path)
    assert "review_events" not in _tables(db)
    shutil.copy2(MIGRATIONS_DIR / "007_review_events.sql", migrations_dir / "007_review_events.sql")
    apply_migrations(db)
    assert {"review_events", "review_event_baseline"} <= _tables(db)
    assert _ledger(db) == {p.name for p in SHIPPED}


# ---------------------------------------------------------------------------
# SEC-03: lifecycle validation does not depend on the event table
# ---------------------------------------------------------------------------

def test_sec03_deleted_review_cannot_be_approved_directly(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        review_id = _insert_review(conn, status="DELETED")
    finally:
        conn.close()
    with pytest.raises(ValidationError, match="transition DELETED -> APPROVED is not allowed"):
        save_review(review_id, {"review_status": "APPROVED", "expected_updated_at": "now"}, db)


def test_sec03_pending_review_can_be_approved_and_is_audited(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        review_id = _insert_review(conn, status="PENDING")
    finally:
        conn.close()
    result = save_review(review_id, {"review_status": "APPROVED", "expected_updated_at": "now", "reviewer": "human"}, db)
    assert result["review_status"] == "APPROVED"
    conn = connect(db)
    try:
        events = conn.execute("SELECT from_status,to_status FROM review_events WHERE review_id=?", (review_id,)).fetchall()
    finally:
        conn.close()
    assert [tuple(e) for e in events] == [("PENDING", "APPROVED")]


def _drop_event_table(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TRIGGER review_events_immutable_update")
    conn.execute("DROP TRIGGER review_events_immutable_delete")
    conn.execute("DROP TABLE review_events")


def test_sec03_lifecycle_guard_applies_without_event_table(tmp_path):
    """The original SEC-03 path: with no review_events table, DELETED -> APPROVED must still fail."""
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        review_id = _insert_review(conn, status="DELETED")
        _drop_event_table(conn)
    finally:
        conn.close()
    with pytest.raises(ValidationError, match="transition DELETED -> APPROVED is not allowed"):
        save_review(review_id, {"review_status": "APPROVED", "reviewer": "human"}, db)
    conn = connect(db)
    try:
        status = conn.execute("SELECT review_status FROM reviews WHERE id=?", (review_id,)).fetchone()[0]
    finally:
        conn.close()
    assert status == "DELETED"


def test_sec03_core_profile_without_event_table_can_still_approve(tmp_path):
    """Core (migrations 001-004) has no event table by design; valid decisions still save."""
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        review_id = _insert_review(conn, status="PENDING")
        _drop_event_table(conn)
    finally:
        conn.close()
    assert save_review(review_id, {"review_status": "APPROVED", "reviewer": "human"}, db)["review_status"] == "APPROVED"
    assert "REVIEW_HISTORY_UNAVAILABLE" in _codes(export_readiness(db))


def test_sec03_resaving_a_decision_with_restriction_is_allowed_and_audited(tmp_path):
    """Marking an approved review as personal data is an edit, not a forbidden transition."""
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        review_id = _insert_review(conn, status="PENDING")
    finally:
        conn.close()
    save_review(review_id, {"review_status": "APPROVED", "reviewer": "human", "training_eligible": True}, db)
    saved = save_review(review_id, {"review_status": "APPROVED", "reviewer": "human", "contains_personal_data": True}, db)
    assert saved["contains_personal_data"] == 1 and saved["training_eligible"] == 0
    save_review(review_id, {"review_status": "FULL_CORRECTION", "corrected_response": "تصحيح", "reviewer": "human"}, db)
    save_review(review_id, {"review_status": "FULL_CORRECTION", "corrected_response": "تصحيح ثان", "reviewer": "human"}, db)
    conn = connect(db)
    try:
        events = conn.execute(
            "SELECT sequence, from_status, to_status FROM review_events WHERE review_id=? ORDER BY sequence", (review_id,)
        ).fetchall()
    finally:
        conn.close()
    assert [tuple(e) for e in events] == [
        (1, "PENDING", "APPROVED"), (2, "APPROVED", "APPROVED"),
        (3, "APPROVED", "FULL_CORRECTION"), (4, "FULL_CORRECTION", "FULL_CORRECTION"),
    ]
    assert not _codes(export_readiness(db)) & {"REVIEW_EVENT_SEQUENCE_CONFLICT", "REVIEW_EVENT_STATUS_CONFLICT"}


@pytest.mark.parametrize("source, target", [("IGNORED", "IGNORED"), ("DELETED", "DELETED"), ("PENDING", "PENDING"),
                                            ("IGNORED", "APPROVED"), ("DELETED", "FULL_CORRECTION")])
def test_sec03_inactive_and_pending_self_or_skip_transitions_stay_forbidden(source, target):
    from app.review_lifecycle import LifecycleError, validate_transition
    with pytest.raises(LifecycleError):
        validate_transition(source, target, "نص", "سبب")


# ---------------------------------------------------------------------------
# SEC-04: bulk manual edits are validated up front and applied atomically
# ---------------------------------------------------------------------------

def _sft_state(db: Path, item_id: int) -> tuple[int, int, int]:
    conn = connect(db)
    try:
        row = conn.execute("SELECT training_eligible, version_number FROM manual_sft_items WHERE id=?", (item_id,)).fetchone()
        versions = conn.execute(
            "SELECT COUNT(*) FROM manual_data_versions WHERE item_type='sft' AND item_id=?", (item_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    return row["training_eligible"], row["version_number"], versions


def test_sec04_intermediate_failure_rolls_back_records_and_versions(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        first = _insert_sft(conn, "أول")
        second = _insert_sft(conn, "ثاني")
    finally:
        conn.close()
    before = (_sft_state(db, first), _sft_state(db, second))
    with pytest.raises(ValidationError):
        bulk_update_manual_data({
            "action": "eligible",
            "items": [{"type": "sft", "id": first}, {"type": "sft", "id": 99999}, {"type": "sft", "id": second}],
        }, db)
    assert (_sft_state(db, first), _sft_state(db, second)) == before


def test_sec04_successful_batch_updates_all_items_with_versions(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        ids = [_insert_sft(conn, f"عنصر {i}") for i in range(3)]
    finally:
        conn.close()
    result = bulk_update_manual_data({"action": "eligible", "items": [{"type": "sft", "id": i} for i in ids]}, db)
    assert result == {"updated": 3}
    for item_id in ids:
        assert _sft_state(db, item_id) == (1, 2, 1)


@pytest.mark.parametrize("bad_item, message", [
    ("not_a_dict", "not a dict"),
    ({"type": "unknown", "id": 1}, "invalid type"),
    ({"type": "sft", "id": "abc"}, "invalid id"),
    ({"type": "sft"}, "invalid id"),
])
def test_sec04_malformed_item_rejects_whole_request(tmp_path, bad_item, message):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        good = _insert_sft(conn, "سليم")
    finally:
        conn.close()
    before = _sft_state(db, good)
    with pytest.raises(ValidationError, match=message):
        bulk_update_manual_data({"action": "eligible", "items": [{"type": "sft", "id": good}, bad_item]}, db)
    assert _sft_state(db, good) == before


def test_sec04_batch_over_500_is_rejected_not_truncated(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        first = _insert_sft(conn, "حد")
    finally:
        conn.close()
    items = [{"type": "sft", "id": first}] + [{"type": "sft", "id": i} for i in range(2, 502)]
    with pytest.raises(ValidationError, match="500"):
        bulk_update_manual_data({"action": "eligible", "items": items}, db)
    assert _sft_state(db, first)[0] == 0


# ---------------------------------------------------------------------------
# SEC-05: review_events is migrated; legacy history is distinguished, not fabricated
# ---------------------------------------------------------------------------

def test_sec05_review_events_are_immutable(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        review_id = _insert_review(conn)
        append_event(conn, review_id=review_id, from_status="PENDING", to_status="APPROVED",
                     actor="tester", original_response="الرد")
        event_id = conn.execute("SELECT id FROM review_events WHERE review_id=?", (review_id,)).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE review_events SET actor='hacker' WHERE id=?", (event_id,))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM review_events WHERE id=?", (event_id,))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM reviews WHERE id=?", (review_id,))
    finally:
        conn.close()


@pytest.fixture
def legacy_db(tmp_path, migrations_dir):
    """A database created before 007 with historical reviews, then upgraded."""
    for path in migrations_dir.glob("007_*.sql"):
        path.unlink()
    db = tmp_path / "legacy.db"
    apply_migrations(db)
    conn = connect(db)
    try:
        ids = {
            "approved": _insert_review(conn, "APPROVED", "legacy-a"),
            "deleted": _insert_review(conn, "DELETED", "legacy-d"),
            "pending": _insert_review(conn, "PENDING", "legacy-p"),
        }
    finally:
        conn.close()
    shutil.copy2(MIGRATIONS_DIR / "007_review_events.sql", migrations_dir / "007_review_events.sql")
    apply_migrations(db)
    return db, ids


def test_sec05_upgrade_records_baseline_and_fabricates_no_events(legacy_db):
    db, ids = legacy_db
    conn = connect(db)
    try:
        baseline = conn.execute("SELECT legacy_max_review_id FROM review_event_baseline").fetchone()[0]
        events = conn.execute("SELECT COUNT(*) FROM review_events").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE review_event_baseline SET legacy_max_review_id=0")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM review_event_baseline")
    finally:
        conn.close()
    assert baseline == max(ids.values())
    assert events == 0


def test_sec05_legacy_reviews_warn_without_blocking(legacy_db):
    db, ids = legacy_db
    result = export_readiness(db)
    missing = {f["sample_id"] for f in result["findings"] if f["code"] == "REVIEW_EVENT_MISSING"}
    unverifiable = {f["sample_id"] for f in result["findings"] if f["code"] == "REVIEW_HISTORY_UNVERIFIABLE"}
    assert not missing
    assert unverifiable == {f"review:{i}" for i in ids.values()}
    # The legacy PENDING review still blocks on its own merits — fail-closed is preserved.
    blocking = {(f["code"], f["sample_id"]) for f in result["blocking_findings"]}
    assert blocking == {("REVIEW_PENDING", f"review:{ids['pending']}")}


def test_sec05_legacy_db_is_ready_once_pending_is_resolved(legacy_db):
    db, ids = legacy_db
    save_review(ids["pending"], {"review_status": "APPROVED", "reviewer": "human"}, db)
    result = export_readiness(db)
    assert result["status"] == "READY", result["blocking_findings"]


def test_sec05_new_review_after_upgrade_requires_events(legacy_db):
    db, _ = legacy_db
    conn = connect(db)
    try:
        new_id = _insert_review(conn, "APPROVED", "post-upgrade")
    finally:
        conn.close()
    result = export_readiness(db)
    assert ("REVIEW_EVENT_MISSING", f"review:{new_id}") in {
        (f["code"], f["sample_id"]) for f in result["blocking_findings"]
    }


def test_sec05_legacy_review_restoration_and_deletion_are_audited(legacy_db):
    db, ids = legacy_db
    restore_review(ids["deleted"], {"reason": "restore legacy", "reviewer": "human"}, db)
    delete_review(ids["approved"], {"reason": "retire legacy", "reviewer": "human"}, db)
    conn = connect(db)
    try:
        rows = conn.execute(
            "SELECT review_id, sequence, from_status, to_status FROM review_events ORDER BY review_id, sequence"
        ).fetchall()
    finally:
        conn.close()
    assert [tuple(r) for r in rows] == sorted([
        (ids["deleted"], 1, "DELETED", "PENDING"),
        (ids["approved"], 1, "APPROVED", "DELETED"),
    ])
    result = export_readiness(db)
    unverifiable = {f["sample_id"] for f in result["findings"] if f["code"] == "REVIEW_HISTORY_UNVERIFIABLE"}
    # Reviews with new events are checked normally; only the untouched one remains unverifiable.
    assert unverifiable == {f"review:{ids['pending']}"}
    assert not {f["code"] for f in result["findings"]} & {
        "REVIEW_EVENT_SEQUENCE_CONFLICT", "REVIEW_EVENT_STATUS_CONFLICT", "REVIEW_EVENT_SOURCE_STALE",
    }


def test_sec05_event_integrity_violations_still_block_legacy_reviews(legacy_db):
    db, ids = legacy_db
    conn = connect(db)
    try:
        # A valid transition whose target disagrees with the stored review status.
        append_event(conn, review_id=ids["approved"], from_status="APPROVED", to_status="IGNORED",
                     actor="human", original_response="الرد", reason="out-of-band write")
    finally:
        conn.close()
    result = export_readiness(db)
    assert ("REVIEW_EVENT_STATUS_CONFLICT", f"review:{ids['approved']}") in {
        (f["code"], f["sample_id"]) for f in result["blocking_findings"]
    }


def test_sec05_missing_baseline_fails_closed(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        review_id = _insert_review(conn, "APPROVED")
        conn.execute("DROP TRIGGER review_event_baseline_immutable_delete")
        conn.execute("DELETE FROM review_event_baseline")
    finally:
        conn.close()
    result = export_readiness(db)
    assert ("REVIEW_EVENT_MISSING", f"review:{review_id}") in {
        (f["code"], f["sample_id"]) for f in result["blocking_findings"]
    }


# ---------------------------------------------------------------------------
# DATA-02 / DATA-03 / DATA-04 / DATA-05 helper-level contracts
# (end-to-end freeze and catalog coverage lives in tests/test_phase_a_dataset_acceptance.py)
# ---------------------------------------------------------------------------

def test_data02_missing_diagnostics_message_is_actionable():
    from app.dataset_platform import _diagnostics_status
    ok, msg = _diagnostics_status(Path("/nonexistent-for-test"), {"version": "gold-test-v001"})
    assert not ok
    assert "not been generated" in (msg or "")


def test_data02_stale_diagnostics_message_is_distinct():
    from app.dataset_platform import _diagnostics_status
    manifest = {
        "version": "gold-test-v001",
        "diagnostics": {"version": "gold-test-DIFFERENT", "training_fingerprint": "abc", "artifacts": {}},
    }
    ok, msg = _diagnostics_status(Path("/nonexistent-for-test"), manifest)
    assert not ok
    assert "stale" in (msg or "")


def test_data03_evaluation_holdout_in_dataset_files():
    from app.dataset_balancer import DATASET_FILES
    assert DATASET_FILES["evaluation_holdout.jsonl"] == "evaluation"


def test_data04_all_consumers_share_platform_file_contract():
    import app.dataset_balancer as balancer
    import app.dataset_platform as platform
    import app.dataset_quality as quality
    import app.unsloth_export as unsloth

    assert quality.EVAL_FILES is platform.EVAL_FILES
    assert quality.KNOWN_FILES is platform.KNOWN_FILES
    assert unsloth.KNOWN_FILES is platform.KNOWN_FILES
    assert {n for n, kind in balancer.DATASET_FILES.items() if kind == "evaluation"} == set(platform.EVAL_FILES)
    assert set(balancer.DATASET_FILES) == set(platform.KNOWN_FILES) | {platform.NATIVE_TRAIN_FILE}


def test_data05_missing_exports_root_is_created(tmp_path, monkeypatch):
    import app.dataset_platform as dp
    monkeypatch.setattr(dp, "EXPORTS_DIR", str(tmp_path / "nonexistent" / "exports"))
    assert dp._exports_root().is_dir()


# ---------------------------------------------------------------------------
# DB-03: backup produces a consistent copy; recovery uses that copy, never a DROP
# ---------------------------------------------------------------------------

def test_db03_backup_preserves_reviews_events_and_baseline(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        review_id = _insert_review(conn, "PENDING")
    finally:
        conn.close()
    save_review(review_id, {"review_status": "APPROVED", "reviewer": "human"}, db)
    dest = backup_db(db, tmp_path / "backup.db")
    conn = connect(dest)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        events = conn.execute("SELECT COUNT(*) FROM review_events WHERE review_id=?", (review_id,)).fetchone()[0]
        baseline = conn.execute("SELECT COUNT(*) FROM review_event_baseline").fetchone()[0]
        ledger = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    finally:
        conn.close()
    assert events == 1 and baseline == 1
    assert ledger == {p.name for p in SHIPPED}


def test_db03_restore_from_verified_backup_recovers_audit_history(tmp_path):
    db = _fresh_db(tmp_path)
    conn = connect(db)
    try:
        review_id = _insert_review(conn, "PENDING")
    finally:
        conn.close()
    save_review(review_id, {"review_status": "APPROVED", "reviewer": "human"}, db)
    backup = backup_db(db, tmp_path / "verified.db")

    # Simulate damage to the live database after the backup was taken.
    db.unlink()
    for suffix in ("-wal", "-shm"):
        Path(f"{db}{suffix}").unlink(missing_ok=True)

    shutil.copy2(backup, db)
    apply_migrations(db)
    conn = connect(db)
    try:
        events = conn.execute("SELECT to_status FROM review_events WHERE review_id=?", (review_id,)).fetchall()
    finally:
        conn.close()
    assert [e[0] for e in events] == ["APPROVED"]
    assert len(_ledger(db)) == len(SHIPPED)


def test_db03_backup_refuses_missing_source_without_creating_it(tmp_path):
    missing = tmp_path / "absent.db"
    with pytest.raises(FileNotFoundError):
        backup_db(missing, tmp_path / "copy.db")
    assert not missing.exists() and not (tmp_path / "copy.db").exists()


def test_db03_backup_never_overwrites_an_existing_backup(tmp_path):
    db = _fresh_db(tmp_path)
    existing = tmp_path / "verified.db"
    existing.write_bytes(b"previous verified backup")
    with pytest.raises(FileExistsError):
        backup_db(db, existing)
    assert existing.read_bytes() == b"previous verified backup"


def test_db03_project_backup_archive_contains_audit_tables_and_exports(tmp_path):
    import zipfile
    from scripts.backup import create_backup

    project = tmp_path / "project"
    (project / "data").mkdir(parents=True)
    db = project / "data" / "najdilab.db"
    apply_migrations(db)
    conn = connect(db)
    try:
        review_id = _insert_review(conn, "PENDING")
    finally:
        conn.close()
    save_review(review_id, {"review_status": "APPROVED", "reviewer": "human"}, db)
    frozen = project / "exports" / "gold-v001"
    frozen.mkdir(parents=True)
    (frozen / "manifest.json").write_text('{"state":"Frozen"}', encoding="utf-8")

    archive = create_backup(project)
    restored = tmp_path / "restored"
    with zipfile.ZipFile(archive) as bundle:
        assert set(bundle.namelist()) == {"data/najdilab.db", "exports/gold-v001/manifest.json"}
        bundle.extractall(restored)
    conn = connect(restored / "data" / "najdilab.db")
    try:
        events = conn.execute("SELECT COUNT(*) FROM review_events").fetchone()[0]
        baseline = conn.execute("SELECT COUNT(*) FROM review_event_baseline").fetchone()[0]
    finally:
        conn.close()
    assert (events, baseline) == (1, 1)
    assert (restored / "exports" / "gold-v001" / "manifest.json").read_text(encoding="utf-8") == '{"state":"Frozen"}'
