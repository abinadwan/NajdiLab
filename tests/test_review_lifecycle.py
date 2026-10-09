import sqlite3
from pathlib import Path

import pytest

from app.review_lifecycle import LifecycleError, append_event, detect_stale_review, validate_transition


SCHEMA = (Path(__file__).resolve().parents[1] / "plans" / "phase2" / "006_review_events.sql").read_text(encoding="utf-8")


def database(tmp_path):
    conn = sqlite3.connect(tmp_path / "reviews.db")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE reviews(id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO reviews VALUES(1)")
    conn.executescript(SCHEMA)
    return conn


def test_explicit_transition_policy():
    validate_transition("PENDING", "APPROVED", None, None)
    validate_transition("DELETED", "PENDING", None, "استعادة بشرية")
    with pytest.raises(LifecycleError):
        validate_transition("DELETED", "APPROVED", None, None)
    with pytest.raises(LifecycleError):
        validate_transition("PENDING", "CONTENT_CORRECTION", None, None)
    with pytest.raises(LifecycleError):
        validate_transition("PENDING", "IGNORED", None, None)


def test_append_only_events_include_hashes_and_sequence(tmp_path):
    conn = database(tmp_path)
    try:
        append_event(conn, review_id=1, from_status="PENDING", to_status="APPROVED", actor="reviewer",
                     original_response="الأصل", error_tags=["dialect_issue", "dialect_issue"])
        append_event(conn, review_id=1, from_status="APPROVED", to_status="DELETED", actor="reviewer",
                     original_response="الأصل", reason="طلب حذف")
        rows = conn.execute("SELECT sequence,to_status,error_tags_json,length(source_sha256) FROM review_events ORDER BY sequence").fetchall()
        assert rows == [(1, "APPROVED", '["dialect_issue"]', 64), (2, "DELETED", "[]", 64)]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE review_events SET actor='changed' WHERE id=1")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM review_events WHERE id=1")
    finally:
        conn.close()


def test_stale_source_detection():
    import hashlib
    expected = hashlib.sha256("الأصل".encode("utf-8")).hexdigest()
    assert not detect_stale_review("الأصل", expected)
    assert detect_stale_review("تغير الأصل", expected)

