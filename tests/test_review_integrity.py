from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request
from tests.http_client import urlopen

import pytest

from app import server as server_module
from app.db import apply_migrations
from app.review_integrity import ExportReadinessError, export_readiness
from app.review_lifecycle import append_event
from app.service import create_export


def fixture_db(tmp_path: Path) -> Path:
    db = tmp_path / "fixture.db"
    apply_migrations(db)
    return db


def insert_review(
    db: Path,
    *,
    status: str = "APPROVED",
    original: str = "الرد الأصلي",
    current: str | None = None,
    corrected: str | None = None,
    eligible: int = 1,
    evaluation: int = 0,
    with_review: bool = True,
    ignore_checks: bool = False,
    with_event: bool = False,
    event_original: str | None = None,
) -> int:
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        if ignore_checks:
            conn.execute("PRAGMA ignore_check_constraints=ON")
        conn.execute(
            "INSERT INTO conversations(external_conversation_id,title,source,channel,created_at,updated_at) VALUES('c1','t','test','test','now','now')"
        )
        conversation_id = conn.execute("SELECT id FROM conversations WHERE external_conversation_id='c1'").fetchone()[0]
        cursor = conn.execute(
            "INSERT INTO messages(conversation_id,turn_index,role,content,created_at) VALUES(?,0,'assistant',?,'now')",
            (conversation_id, current if current is not None else original),
        )
        if not with_review:
            return cursor.lastrowid
        review = conn.execute(
            """
            INSERT INTO reviews(message_id,review_status,original_response,corrected_response,reviewer,
              training_eligible,evaluation_only,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (cursor.lastrowid, status, original, corrected, "human", eligible, evaluation, "now", "now"),
        )
        review_id = review.lastrowid
        if with_event:
            append_event(conn, review_id=review_id, from_status="PENDING", to_status=status,
                         actor="human", original_response=event_original if event_original is not None else original,
                         corrected_response=corrected)
        return review_id


def codes(result):
    return {item["code"] for item in result["findings"]}


def test_approved_review_is_ready_when_event_is_recorded(tmp_path):
    # SEC-05 regression: review_events table always exists after migration;
    # an approved review with a recorded event must be READY (not BLOCKED).
    db = fixture_db(tmp_path)
    insert_review(db, with_event=True)
    result = export_readiness(db)
    assert result["status"] == "READY"
    assert result["counts"]["blocking"] == 0
    assert "REVIEW_EVENT_MISSING" not in codes(result)
    assert "REVIEW_HISTORY_UNAVAILABLE" not in codes(result)


def test_approved_review_without_event_is_blocked(tmp_path):
    # SEC-05 regression: when review_events table exists but a review has no event,
    # export must be BLOCKED — the integrity check catches missing audit trails.
    db = fixture_db(tmp_path)
    insert_review(db)
    result = export_readiness(db)
    assert result["status"] == "BLOCKED"
    assert "REVIEW_EVENT_MISSING" in codes(result)


def test_pending_review_blocks_with_actionable_sample_id(tmp_path):
    db = fixture_db(tmp_path)
    review_id = insert_review(db, status="PENDING", eligible=0)
    result = export_readiness(db)
    assert result["status"] == "BLOCKED"
    finding = next(item for item in result["blocking_findings"] if item["code"] == "REVIEW_PENDING")
    assert finding["sample_id"] == f"review:{review_id}"
    assert finding["severity"] == "ERROR" and finding["confirmed"] is True


def test_conflicting_flags_block(tmp_path):
    db = fixture_db(tmp_path)
    insert_review(db, eligible=1, evaluation=1, ignore_checks=True)
    result = export_readiness(db)
    assert "REVIEW_SPLIT_CONFLICT" in codes(result)
    assert result["status"] == "BLOCKED"


def test_semantic_stale_blocks_but_format_drift_is_ambiguous(tmp_path):
    stale_db = fixture_db(tmp_path / "stale")
    insert_review(stale_db, original="النص الأول", current="نص مختلف")
    stale = export_readiness(stale_db)
    assert "REVIEW_SOURCE_STALE" in codes(stale) and stale["status"] == "BLOCKED"

    format_db = fixture_db(tmp_path / "format")
    # event_original matches message content so REVIEW_EVENT_SOURCE_STALE is not triggered;
    # the review snapshot still differs (triple-space vs single) → FORMAT_DRIFT warning only
    insert_review(format_db, original="رد   موثّق", current="رد موثّق",
                  with_event=True, event_original="رد موثّق")
    drift = export_readiness(format_db)
    assert "REVIEW_SOURCE_FORMAT_DRIFT" in codes(drift)
    assert drift["status"] == "READY"


def test_missing_review_and_missing_database_fail_closed(tmp_path):
    db = fixture_db(tmp_path / "missing-review")
    insert_review(db, with_review=False)
    result = export_readiness(db)
    assert "REVIEW_MISSING" in codes(result)
    assert "NO_EXPORTABLE_DATA" in codes(result)
    assert result["status"] == "BLOCKED"

    missing = export_readiness(tmp_path / "does-not-exist.db")
    assert missing["status"] == "BLOCKED"
    assert "DATABASE_UNAVAILABLE" in codes(missing)


def test_create_export_blocks_before_writing_and_preserves_frozen_release(tmp_path):
    db = fixture_db(tmp_path)
    insert_review(db, status="PENDING", eligible=0)
    exports = tmp_path / "exports"
    frozen = exports / "gold-v999-frozen"
    frozen.mkdir(parents=True)
    protected = frozen / "manifest.json"
    protected.write_text('{"state":"Frozen"}', encoding="utf-8")
    before = hashlib.sha256(protected.read_bytes()).hexdigest()
    with pytest.raises(ExportReadinessError) as error:
        create_export(db, exports)
    assert error.value.readiness["status"] == "BLOCKED"
    assert sorted(path.name for path in exports.iterdir()) == ["gold-v999-frozen"]
    assert hashlib.sha256(protected.read_bytes()).hexdigest() == before


def test_missing_review_tables_fail_closed(tmp_path):
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    result = export_readiness(db)
    assert result["status"] == "BLOCKED"
    assert "REVIEW_DATA_UNAVAILABLE" in codes(result)


def test_history_conflicts_and_transaction_rollback_are_detected_safely(tmp_path):
    db = fixture_db(tmp_path)
    review_id = insert_review(db)
    schema = (Path(__file__).parents[1] / "plans" / "phase2" / "006_review_events.sql").read_text(encoding="utf-8")
    with sqlite3.connect(db) as conn:
        conn.executescript(schema)
        conn.execute(
            """
            INSERT INTO review_events(review_id,sequence,from_status,to_status,actor,error_tags_json,
              source_sha256,created_at) VALUES(?,2,'PENDING','PENDING','reviewer','[]',?,'now')
            """,
            (review_id, "0" * 64),
        )
    result = export_readiness(db)
    assert {"REVIEW_EVENT_SEQUENCE_CONFLICT", "REVIEW_EVENT_STATUS_CONFLICT", "REVIEW_EVENT_SOURCE_STALE"} <= codes(result)
    assert result["status"] == "BLOCKED"

    with sqlite3.connect(db) as conn:
        before = conn.execute("SELECT COUNT(*) FROM review_events").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            with conn:
                conn.execute(
                    """
                    INSERT INTO review_events(review_id,sequence,from_status,to_status,actor,error_tags_json,
                      source_sha256,created_at) VALUES(?,3,'PENDING','APPROVED','reviewer','[]',?,'now')
                    """,
                    (review_id, "1" * 64),
                )
                conn.execute(
                    """
                    INSERT INTO review_events(review_id,sequence,from_status,to_status,actor,error_tags_json,
                      source_sha256,created_at) VALUES(?,3,'PENDING','APPROVED','reviewer','[]',?,'now')
                    """,
                    (review_id, "1" * 64),
                )
        assert conn.execute("SELECT COUNT(*) FROM review_events").fetchone()[0] == before


def test_dashboard_surfaces_readiness_and_blocks_client_export():
    source = (Path(__file__).parents[1] / "static" / "app.js").read_text(encoding="utf-8")
    assert "/api/v1/exports/readiness" in source
    assert "if(!readiness.ok)" in source
    assert "blocking_findings" in source


def test_http_readiness_and_export_return_structured_blockers(tmp_path):
    db = fixture_db(tmp_path)
    review_id = insert_review(db, status="PENDING", eligible=0)
    with patch.object(server_module, "DB_PATH", db):
        server = server_module.NajdiLabHTTPServer(("127.0.0.1", 0), server_module.NajdiLabHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(base + "/api/v1/exports/readiness", timeout=10) as response:
                readiness = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert readiness["status"] == "BLOCKED"
            assert any(item["sample_id"] == f"review:{review_id}" for item in readiness["blocking_findings"])

            request = Request(
                base + "/api/v1/exports",
                data=b'{}',
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with pytest.raises(HTTPError) as raised:
                urlopen(request, timeout=10)
            payload = json.loads(raised.value.read().decode("utf-8"))
            assert raised.value.code == 409
            assert payload["code"] == "EXPORT_NOT_READY"
            assert payload["readiness"]["status"] == "BLOCKED"
            assert payload["readiness"]["blocking_findings"]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

