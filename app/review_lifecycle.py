from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

PENDING = "PENDING"
CORRECTIONS = frozenset({"FULL_CORRECTION", "DIALECT_CORRECTION", "CONTENT_CORRECTION"})
DECISIONS = frozenset({"APPROVED", *CORRECTIONS})
INACTIVE = frozenset({"IGNORED", "DELETED"})
STATUSES = frozenset({PENDING, *DECISIONS, *INACTIVE})

# A decision may be re-saved with the same status (edited text or restriction flags);
# that edit is recorded as an event like any other decision.
ALLOWED_TRANSITIONS = {
    PENDING: DECISIONS | INACTIVE,
    "APPROVED": DECISIONS | INACTIVE,
    "FULL_CORRECTION": DECISIONS | INACTIVE,
    "DIALECT_CORRECTION": DECISIONS | INACTIVE,
    "CONTENT_CORRECTION": DECISIONS | INACTIVE,
    "IGNORED": {PENDING},
    "DELETED": {PENDING},
}


class LifecycleError(ValueError):
    pass


def validate_transition(from_status: str, to_status: str, corrected_response: str | None, reason: str | None) -> None:
    if from_status not in STATUSES or to_status not in STATUSES:
        raise LifecycleError("unknown review status")
    if to_status not in ALLOWED_TRANSITIONS[from_status]:
        raise LifecycleError(f"transition {from_status} -> {to_status} is not allowed")
    if to_status in CORRECTIONS and not str(corrected_response or "").strip():
        raise LifecycleError("correction transitions require corrected_response")
    if to_status in INACTIVE and not str(reason or "").strip():
        raise LifecycleError("ignore/delete transitions require a reason")
    if from_status in INACTIVE and to_status == PENDING and not str(reason or "").strip():
        raise LifecycleError("restore requires a reason")


def sha256_text(value: str | None) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value is not None else None


def append_event(
    conn: sqlite3.Connection,
    *,
    review_id: int,
    from_status: str,
    to_status: str,
    actor: str,
    original_response: str,
    corrected_response: str | None = None,
    reason: str | None = None,
    error_tags: list[str] | None = None,
) -> int:
    validate_transition(from_status, to_status, corrected_response, reason)
    if not actor.strip():
        raise LifecycleError("actor is required")
    sequence = conn.execute(
        "SELECT COALESCE(MAX(sequence), 0) + 1 FROM review_events WHERE review_id=?", (review_id,)
    ).fetchone()[0]
    cursor = conn.execute(
        "INSERT INTO review_events(review_id,sequence,from_status,to_status,actor,reason,correction_type,"
        "error_tags_json,source_sha256,correction_sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (review_id, sequence, from_status, to_status, actor.strip(), reason,
         to_status if to_status in CORRECTIONS else None,
         json.dumps(sorted(set(error_tags or [])), ensure_ascii=False), sha256_text(original_response),
         sha256_text(corrected_response), datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
    )
    return int(cursor.lastrowid)


def detect_stale_review(original_response: str, recorded_source_sha256: str) -> bool:
    return sha256_text(original_response) != recorded_source_sha256

