from __future__ import annotations

import sqlite3
import json
import threading
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request
from tests.http_client import urlopen

import pytest

from app.db import apply_migrations
from app import server as server_module
from app.review_integrity import export_readiness
from app.service import (
    ValidationError,
    approve_review,
    bulk_review_actions,
    correct_review,
    exclude_review,
    get_review,
    restore_review,
)


def fixture_db(tmp_path: Path, *, events: bool = False) -> Path:
    db = tmp_path / "reviews.db"
    apply_migrations(db)
    if events:
        schema = (Path(__file__).parents[1] / "plans" / "phase2" / "006_review_events.sql").read_text(encoding="utf-8")
        with sqlite3.connect(db) as conn:
            conn.executescript(schema)
    return db


def add_pending(db: Path, suffix: str) -> int:
    with sqlite3.connect(db) as conn:
        conversation = conn.execute(
            "INSERT INTO conversations(external_conversation_id,title,source,channel,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (f"c-{suffix}", f"محادثة {suffix}", "test", "test", "now", "now"),
        ).lastrowid
        message = conn.execute(
            "INSERT INTO messages(conversation_id,turn_index,role,content,created_at) VALUES(?,0,'assistant',?,'now')",
            (conversation, f"الأصل {suffix}"),
        ).lastrowid
        return conn.execute(
            "INSERT INTO reviews(message_id,original_response,created_at,updated_at) VALUES(?,?,?,?)",
            (message, f"الأصل {suffix}", "now", "now"),
        ).lastrowid


def snapshot(db: Path, review_id: int) -> tuple:
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT review_status,original_response,corrected_response,reviewer,updated_at FROM reviews WHERE id=?",
            (review_id,),
        ).fetchone()


def test_original_is_immutable_and_correction_metadata_is_retained(tmp_path):
    db = fixture_db(tmp_path, events=True)
    review_id = add_pending(db, "metadata")
    before = snapshot(db, review_id)
    result = correct_review(
        review_id,
        {
            "review_status": "DIALECT_CORRECTION",
            "corrected_response": "التصحيح النجدي",
            "reviewer": "human",
            "reviewer_identity": "reviewer-17",
            "review_notes": "تصحيح الصياغة",
            "tags": ["dialect_issue", "grammar_issue"],
        },
        db,
    )
    after = snapshot(db, review_id)
    assert after[1] == before[1] == "الأصل metadata"
    assert result["corrected_response"] == "التصحيح النجدي"
    assert result["reviewer"] == "human"
    assert set(result["tags"]) == {"dialect_issue", "grammar_issue"}
    with sqlite3.connect(db) as conn:
        event = conn.execute(
            "SELECT actor,correction_type,error_tags_json,created_at FROM review_events WHERE review_id=?",
            (review_id,),
        ).fetchone()
    assert event[0] == "reviewer-17"
    assert event[1] == "DIALECT_CORRECTION"
    assert "dialect_issue" in event[2]
    assert event[3]


def test_exclude_restore_preserves_original_and_prior_correction(tmp_path):
    db = fixture_db(tmp_path)
    review_id = add_pending(db, "restore")
    correct_review(review_id, {"review_status": "CONTENT_CORRECTION", "corrected_response": "تصحيح محفوظ"}, db)
    exclude_review(review_id, {"reason": "مراجعة ثانية مطلوبة"}, db)
    restored = restore_review(review_id, {"reason": "إعادة إلى الطابور"}, db)
    assert restored["review_status"] == "PENDING"
    assert restored["original_response"] == "الأصل restore"
    assert restored["corrected_response"] == "تصحيح محفوظ"
    readiness = export_readiness(db)
    assert readiness["status"] == "BLOCKED"
    assert {"REVIEW_PENDING", "REVIEW_PRESERVED_CORRECTION_PENDING"} <= {item["code"] for item in readiness["findings"]}


def test_bulk_approve_is_atomic_and_integrates_with_readiness(tmp_path):
    db = fixture_db(tmp_path)
    ids = [add_pending(db, str(index)) for index in range(3)]
    result = bulk_review_actions({"action": "approve", "review_ids": ids, "reviewer": "human", "training_eligible": True}, db)
    assert result["count"] == 3
    assert {get_review(review_id, db)["review_status"] for review_id in ids} == {"APPROVED"}
    assert export_readiness(db)["status"] == "READY"


def test_bulk_failure_rolls_back_every_review_and_tag(tmp_path):
    db = fixture_db(tmp_path)
    first = add_pending(db, "rollback-1")
    second = add_pending(db, "rollback-2")
    before = {review_id: snapshot(db, review_id) for review_id in (first, second)}
    with pytest.raises(ValidationError):
        bulk_review_actions(
            {"action": "correct", "review_ids": [first, 999999, second], "review_status": "FULL_CORRECTION", "corrected_response": "لن يُحفظ", "tags": ["other"]},
            db,
        )
    assert {review_id: snapshot(db, review_id) for review_id in (first, second)} == before
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM review_tags").fetchone()[0] == 0


def test_bulk_restore_rejects_mixed_state_and_rolls_back(tmp_path):
    db = fixture_db(tmp_path)
    excluded = add_pending(db, "excluded")
    pending = add_pending(db, "pending")
    exclude_review(excluded, {"reason": "اختبار"}, db)
    with pytest.raises(ValidationError):
        bulk_review_actions({"action": "restore", "review_ids": [excluded, pending], "reason": "إعادة"}, db)
    assert get_review(excluded, db)["review_status"] == "IGNORED"
    assert get_review(pending, db)["review_status"] == "PENDING"


def test_optimistic_timestamp_prevents_overwriting_newer_decision(tmp_path):
    db = fixture_db(tmp_path)
    review_id = add_pending(db, "concurrency")
    with pytest.raises(ValidationError):
        approve_review(review_id, {"expected_updated_at": "stale-timestamp"}, db)
    assert get_review(review_id, db)["review_status"] == "PENDING"


def test_ui_contract_has_all_actions_metadata_and_bulk_controls():
    root = Path(__file__).parents[1] / "static"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    for marker in ("approve-review", "edit-review", "exclude-review", "reviewer-identity", "bulk-exclude-reviews", "bulk-restore-reviews"):
        assert marker in html
    for endpoint in ("'approve'", "'correct'", "'exclude'", "'restore'", "/api/v1/reviews/bulk"):
        assert endpoint in js
    assert "item.corrected_response||item.original_response" in js


def test_http_bulk_and_restore_actions_use_structured_contract(tmp_path):
    db = fixture_db(tmp_path)
    first, second = add_pending(db, "http-1"), add_pending(db, "http-2")
    exclude_review(first, {"reason": "قبل الاستعادة"}, db)
    bindings = {
        "bulk_review_actions": lambda data: bulk_review_actions(data, db),
        "restore_review": lambda review_id, data: restore_review(review_id, data, db),
    }
    patches = [patch.object(server_module, name, value) for name, value in bindings.items()]
    for active in patches:
        active.start()
    server = server_module.NajdiLabHTTPServer(("127.0.0.1", 0), server_module.NajdiLabHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def post(path: str, payload: dict) -> dict:
            request = Request(
                f"http://127.0.0.1:{server.server_address[1]}{path}",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))

        restored = post(f"/api/v1/reviews/{first}/restore", {"reason": "إعادة HTTP"})
        assert restored["review"]["review_status"] == "PENDING"
        bulk = post("/api/v1/reviews/bulk", {"action": "approve", "review_ids": [first, second], "training_eligible": True})
        assert bulk["ok"] is True and bulk["count"] == 2
        assert export_readiness(db)["status"] == "READY"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        for active in reversed(patches):
            active.stop()

