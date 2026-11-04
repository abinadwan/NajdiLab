from __future__ import annotations

from contextlib import nullcontext

import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from uuid import uuid4

from .db import DB_PATH, ROOT, connect, json_dumps, json_loads, redact_secrets, transaction, utc_now
from .review_integrity import ExportReadinessError, export_readiness, export_privacy
from .review_lifecycle import append_event, validate_transition, LifecycleError
from .collection_context import collection_context, INCOMPLETE_CONTEXT_WARNING

CORRECTION_REVIEW_STATUSES = {
    "FULL_CORRECTION",
    "DIALECT_CORRECTION",
    "CONTENT_CORRECTION",
}
TRAINING_REVIEW_STATUSES = {
    "APPROVED",
    *CORRECTION_REVIEW_STATUSES,
}
REVIEW_STATUSES = {"PENDING", "IGNORED", "DELETED", *TRAINING_REVIEW_STATUSES}
FINAL_REVIEW_STATUSES = TRAINING_REVIEW_STATUSES
ERROR_TAGS = {
    "forgot_previous_constraint",
    "ignored_user_instruction",
    "wrong_context",
    "repeated_rejected_option",
    "contradiction",
    "hallucination",
    "dialect_issue",
    "grammar_issue",
    "unnatural_arabic",
    "too_verbose",
    "too_short",
    "format_failure",
    "factual_error",
    "other",
}
ORIGINS = {"real_conversation", "manual", "human_corrected", "synthetic_reviewed", "ai_arena", "imported"}
LANGUAGE_LAYERS = {"najdi_riyadh", "saudi_neutral", "msa", "technical_arabic", "formal_arabic"}
MANUAL_TABLES = {
    "sft": "manual_sft_items",
    "direct": "direct_language_texts",
    "dpo": "preference_pairs",
}
MANUAL_TYPES_BY_TABLE = {table: item_type for item_type, table in MANUAL_TABLES.items()}
EXPORT_SPLIT_SEED = 42
EXPORT_EVALUATION_FRACTION = 0.12
EXPORT_MIN_AUTO_SPLIT_RECORDS = 20
EXPORT_EVALUATION_PER_CONVERSATION_CAP = 8
EXPORT_MULTI_TURN_PER_CONVERSATION_CAP = 10
REVIEW_DEDUP_PRIORITY = {
    "APPROVED": 4,
    "FULL_CORRECTION": 3,
    "DIALECT_CORRECTION": 2,
    "CONTENT_CORRECTION": 1,
}


class ValidationError(ValueError):
    pass


PAGE_DEFAULT_LIMIT = 100
PAGE_MAX_LIMIT = 500


def page_request(query: dict[str, Any]) -> tuple[int, int]:
    """Read `limit`/`offset` from a query; out-of-range values are rejected, never clamped."""
    def number(name: str, default: int, low: int, high: int) -> int:
        raw = query.get(name)
        if raw is None or raw == "":
            return default
        try:
            value = int(str(raw))
        except ValueError:
            raise ValidationError(f"{name} must be an integer") from None
        if not low <= value <= high:
            raise ValidationError(f"{name} must be between {low} and {high}")
        return value
    return number("limit", PAGE_DEFAULT_LIMIT, 1, PAGE_MAX_LIMIT), number("offset", 0, 0, 10**9)


def page_info(total: int, limit: int, offset: int, returned: int) -> dict[str, Any]:
    return {"total": total, "limit": limit, "offset": offset, "returned": returned,
            "has_more": offset + returned < total, "max_limit": PAGE_MAX_LIMIT}


def _bool(value: Any) -> int:
    return int(bool(value))


def _required(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if value is None or not str(value).strip():
        raise ValidationError(f"Required field: {key}")
    return str(value).strip()


def _reviewer(data: dict[str, Any]) -> str:
    reviewer = str(data.get("reviewer") or "human")
    if reviewer not in {"human", "ai_suggestion", "import"}:
        raise ValidationError("Invalid reviewer identity")
    return reviewer


def _conversation_row(conn: sqlite3.Connection, external_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM conversations WHERE external_conversation_id = ?", (external_id,)
    ).fetchone()


def create_conversation(data: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    external_id = str(data.get("external_conversation_id") or data.get("conversation_id") or uuid4())
    now = utc_now()
    metadata = redact_secrets(data.get("metadata") or {})
    conn = connect(db_path)
    try:
        with transaction(conn):
            existing = _conversation_row(conn, external_id)
            if existing:
                return dict(existing)
            cursor = conn.execute(
                """
                INSERT INTO conversations(
                    external_conversation_id, title, source, channel, provider, model_name,
                    model_version, system_prompt_version, created_at, updated_at, metadata_json, demo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    external_id,
                    data.get("title") or f"Conversation {external_id[:12]}",
                    data.get("source") or "manual",
                    data.get("channel") or "manual",
                    data.get("provider"),
                    data.get("model_name"),
                    data.get("model_version"),
                    data.get("system_prompt_version"),
                    now,
                    now,
                    json_dumps(metadata),
                    _bool(data.get("demo")),
                ),
            )
            return dict(conn.execute("SELECT * FROM conversations WHERE id = ?", (cursor.lastrowid,)).fetchone())
    finally:
        conn.close()


def add_message(data: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    role = _required(data, "role")
    if role not in {"system", "user", "assistant", "tool"}:
        raise ValidationError("Invalid role")
    content = _required(data, "content")
    conn = connect(db_path)
    try:
        with transaction(conn):
            conversation_id = data.get("conversation_id")
            if isinstance(conversation_id, str) and not conversation_id.isdigit():
                row = _conversation_row(conn, conversation_id)
                if not row:
                    raise ValidationError("Conversation not found")
                conversation_id = row["id"]
            if not conversation_id:
                raise ValidationError("conversation_id is required")
            next_turn = conn.execute(
                "SELECT COALESCE(MAX(turn_index), -1) + 1 FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()[0]
            turn_index = int(data.get("turn_index", next_turn))
            cursor = conn.execute(
                """
                INSERT INTO messages(
                    conversation_id, turn_index, role, content, provider, model_name, model_version,
                    created_at, generation_settings_json, token_usage_json, latency_ms,
                    source_message_id, metadata_json, parent_message_id, candidate_group_id, judge_result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    turn_index,
                    role,
                    content,
                    data.get("provider"),
                    data.get("model_name"),
                    data.get("model_version"),
                    data.get("created_at") or utc_now(),
                    json_dumps(redact_secrets(data.get("generation_settings") or {})),
                    json_dumps(data.get("token_usage") or {}),
                    data.get("latency_ms"),
                    data.get("source_message_id"),
                    json_dumps(redact_secrets(data.get("metadata") or {})),
                    data.get("parent_message_id"),
                    data.get("candidate_group_id"),
                    json_dumps(data.get("judge_result") or {}),
                ),
            )
            message_id = cursor.lastrowid
            if role == "assistant":
                now = utc_now()
                conn.execute(
                    """INSERT INTO reviews(message_id, original_response, created_at, updated_at)
                    VALUES (?, ?, ?, ?)""",
                    (message_id, content, now, now),
                )
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (utc_now(), conversation_id))
            return dict(conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone())
    finally:
        conn.close()


def ingest_turn(data: dict[str, Any], db_path: Path | str = DB_PATH, *, _connection=None, _preserve_text=False) -> dict[str, Any]:
    external_id = _required(data, "conversation_id")
    user_message = _required(data, "user_message")
    assistant_response = _required(data, "assistant_response")
    if _preserve_text:
        # Internal raw-chat entry: validate without stripping the source text.
        if any(not isinstance(data.get(k), str) or not data[k].strip() for k in ("user_message", "assistant_response")):
            raise ValidationError("Completed chat text must be a nonblank string")
        user_message, assistant_response = data["user_message"], data["assistant_response"]
    source_message_id = str(data.get("source_message_id") or "").strip() or None
    conn = _connection if _connection is not None else connect(db_path)
    try:
        with (nullcontext(conn) if _connection is not None else transaction(conn)):
            conversation = _conversation_row(conn, external_id)
            now = utc_now()
            if conversation and source_message_id:
                existing = conn.execute(
                    """
                    SELECT m.id AS assistant_message_id, r.id AS review_id, r.review_status
                    FROM messages m JOIN reviews r ON r.message_id = m.id
                    WHERE m.conversation_id = ? AND m.role = 'assistant' AND m.source_message_id = ?
                    """,
                    (conversation["id"], source_message_id),
                ).fetchone()
                if existing:
                    return {
                        "conversation_id": conversation["id"],
                        "external_conversation_id": external_id,
                        "assistant_message_id": existing["assistant_message_id"],
                        "review_id": existing["review_id"],
                        "review_status": existing["review_status"],
                        "duplicate": True,
                    }
            if not conversation:
                cursor = conn.execute(
                    """
                    INSERT INTO conversations(
                        external_conversation_id, title, source, channel, provider, model_name,
                        model_version, system_prompt_version, created_at, updated_at, metadata_json, demo
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        external_id,
                        data.get("title") or f"Conversation {external_id[:12]}",
                        data.get("source") or "api",
                        data.get("channel") or "api",
                        data.get("provider"),
                        data.get("model_name"),
                        data.get("model_version"),
                        data.get("system_prompt_version"),
                        now,
                        now,
                        json_dumps(redact_secrets(data.get("metadata") or {})),
                        _bool(data.get("demo")),
                    ),
                )
                conversation_id = cursor.lastrowid
            else:
                conversation_id = conversation["id"]
            reply_to_message_id = data.get("reply_to_message_id") or data.get("parent_message_id")
            reply_to_source_message_id = str(data.get("reply_to_source_message_id") or "").strip()
            if reply_to_source_message_id:
                linked = conn.execute(
                    """
                    SELECT id FROM messages
                    WHERE conversation_id = ? AND role = 'assistant' AND source_message_id = ?
                    ORDER BY turn_index DESC LIMIT 1
                    """,
                    (conversation_id, reply_to_source_message_id),
                ).fetchone()
                if not linked:
                    raise ValidationError("reply_to_source_message_id does not identify an assistant message in this conversation")
                reply_to_message_id = linked["id"]
            if reply_to_message_id is not None:
                linked = conn.execute(
                    "SELECT id FROM messages WHERE id = ? AND conversation_id = ? AND role = 'assistant'",
                    (reply_to_message_id, conversation_id),
                ).fetchone()
                if not linked:
                    raise ValidationError("reply_to_message_id does not identify an assistant message in this conversation")
                reply_to_message_id = linked["id"]
            next_turn = conn.execute(
                "SELECT COALESCE(MAX(turn_index), -1) + 1 FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()[0]
            message_created_at = data.get("created_at") or now
            common = (
                data.get("provider"),
                data.get("model_name"),
                data.get("model_version"),
                message_created_at,
            )
            user_cursor = conn.execute(
                """
                INSERT INTO messages(
                    conversation_id, turn_index, role, content, provider, model_name, model_version,
                    created_at, generation_settings_json, token_usage_json, source_message_id, metadata_json,
                    parent_message_id, candidate_group_id, judge_result_json
                ) VALUES (?, ?, 'user', ?, ?, ?, ?, ?, '{}', '{}', ?, ?, ?, ?, '{}')
                """,
                (
                    conversation_id,
                    next_turn,
                    user_message,
                    *common,
                    source_message_id,
                    json_dumps(redact_secrets(data.get("user_metadata") or {})),
                    reply_to_message_id,
                    data.get("candidate_group_id"),
                ),
            )
            assistant_cursor = conn.execute(
                """
                INSERT INTO messages(
                    conversation_id, turn_index, role, content, provider, model_name, model_version,
                    created_at, generation_settings_json, token_usage_json, latency_ms, source_message_id, metadata_json,
                    parent_message_id, candidate_group_id, judge_result_json
                ) VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    next_turn + 1,
                    assistant_response,
                    *common,
                    json_dumps(redact_secrets(data.get("generation_settings") or {})),
                    json_dumps(data.get("token_usage") or {}),
                    data.get("latency_ms"),
                    source_message_id,
                    json_dumps(redact_secrets(data.get("metadata") or {})),
                    user_cursor.lastrowid,
                    data.get("candidate_group_id"),
                    json_dumps(data.get("judge_result") or {}),
                ),
            )
            review_cursor = conn.execute(
                """INSERT INTO reviews(message_id, original_response, created_at, updated_at)
                VALUES (?, ?, ?, ?)""",
                (assistant_cursor.lastrowid, assistant_response, now, now),
            )
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
            return {
                "conversation_id": conversation_id,
                "external_conversation_id": external_id,
                "user_message_id": user_cursor.lastrowid,
                "assistant_message_id": assistant_cursor.lastrowid,
                "review_id": review_cursor.lastrowid,
                "review_status": "PENDING",
                "duplicate": False,
            }
    finally:
        if _connection is None:
            conn.close()


def ingest_hermes_hook(data: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    if data.get("hook_event_name") != "post_llm_call":
        raise ValidationError("The Hermes endpoint only supports the post_llm_call event")
    extra = data.get("extra")
    if not isinstance(extra, dict):
        raise ValidationError("Hermes hook extra is required")
    user_message = _required(extra, "user_message")
    assistant_response = _required(extra, "assistant_response")
    profile = str(data.get("profile") or "default").strip() or "default"
    conversation_hash = str(extra.get("conversation_key_hash") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", conversation_hash):
        safe_fallback = str(data.get("session_id") or data.get("delivery_id") or uuid4())
        conversation_hash = hashlib.sha256(safe_fallback.encode("utf-8")).hexdigest()
    platform = str(extra.get("platform") or "other").strip().lower()
    channel = {
        "whatsapp": "whatsapp",
        "telegram": "telegram",
        "api_server": "web",
        "web": "web",
        "local": "private",
        "desktop": "private",
        "tui": "private",
    }.get(platform, "other")
    turn_id = str(extra.get("turn_id") or data.get("delivery_id") or "").strip()
    acceptance_test = bool(extra.get("acceptance_test"))
    metadata = {
        "hermes_profile": profile,
        "hermes_session_id": str(data.get("session_id") or ""),
        "hermes_turn_id": turn_id,
        "delivery_id": str(data.get("delivery_id") or ""),
        "channel_kind": channel,
        "acceptance_test": acceptance_test,
    }
    return ingest_turn(
        {
            "conversation_id": f"hermes:{profile}:{conversation_hash}",
            "title": f"Hermes {channel} · {conversation_hash[:10]}",
            "source": "hermes",
            "channel": channel,
            "provider": extra.get("provider"),
            "model_name": extra.get("model"),
            "model_version": extra.get("model_version"),
            "system_prompt_version": extra.get("system_prompt_version"),
            "user_message": user_message,
            "assistant_response": assistant_response,
            "generation_settings": extra.get("generation_settings") if isinstance(extra.get("generation_settings"), dict) else {},
            "source_message_id": turn_id or None,
            "reply_to_source_message_id": str(extra.get("reply_to_message_id") or "").strip() or None,
            "created_at": data.get("timestamp"),
            "metadata": metadata,
            "demo": acceptance_test,
        },
        db_path,
    )


def _message_context(conn: sqlite3.Connection, message_id: int) -> list[dict[str, Any]]:
    message = conn.execute("SELECT conversation_id, turn_index FROM messages WHERE id = ?", (message_id,)).fetchone()
    if not message:
        raise ValidationError("Message not found")
    rows = conn.execute(
        """
        SELECT id, turn_index, role, content, provider, model_name, model_version, created_at
        FROM messages WHERE conversation_id = ? AND turn_index <= ? ORDER BY turn_index
        """,
        (message["conversation_id"], message["turn_index"]),
    ).fetchall()
    return [dict(row) for row in rows]


def _review_collection_context(conn: sqlite3.Connection, message_id: int) -> dict[str, Any]:
    row = conn.execute('''SELECT c.source, c.metadata_json FROM conversations c
        JOIN messages m ON m.conversation_id=c.id WHERE m.id=?''', (message_id,)).fetchone()
    return collection_context(row) if row else {}


def list_review_queue(db_path: Path | str = DB_PATH, include_demo: bool = True) -> list[dict[str, Any]]:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT r.*, m.conversation_id, m.turn_index, m.created_at AS message_created_at,
                   m.provider AS message_provider, m.model_name AS message_model_name,
                   c.external_conversation_id, c.title AS conversation_title, c.source, c.channel,
                   c.provider, c.model_name, c.demo,
                   (SELECT content FROM messages u WHERE u.conversation_id = m.conversation_id
                    AND u.role = 'user' AND u.turn_index < m.turn_index
                    ORDER BY u.turn_index DESC LIMIT 1) AS user_message
            FROM reviews r
            JOIN messages m ON m.id = r.message_id
            JOIN conversations c ON c.id = m.conversation_id
            WHERE r.review_status = 'PENDING' AND (? = 1 OR c.demo = 0)
            ORDER BY m.created_at, r.id
            """,
            (_bool(include_demo),),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["tags"] = [
                value[0] for value in conn.execute("SELECT tag FROM review_tags WHERE review_id = ?", (row["id"],))
            ]
            item["context"] = _message_context(conn, row["message_id"])
            item.update(_review_collection_context(conn, row["message_id"]))
            result.append(item)
        return result
    finally:
        conn.close()


def save_review(review_id: int, data: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        with transaction(conn):
            return _save_review_conn(conn, review_id, data, db_path)
    finally:
        conn.close()


def _has_review_events(conn: sqlite3.Connection) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='review_events'"
    ).fetchone() is not None


def _record_review_event(
    conn: sqlite3.Connection,
    current: sqlite3.Row,
    to_status: str,
    data: dict[str, Any],
    *,
    reason: str | None = None,
    corrected_response: str | None = None,
    tags: list[str] | None = None,
) -> None:
    # The Core profile (migrations 001-004) intentionally has no event table; readiness
    # reports that as REVIEW_HISTORY_UNAVAILABLE. The full app always has it after startup.
    if not _has_review_events(conn):
        return
    append_event(
        conn,
        review_id=int(current["id"]),
        from_status=str(current["review_status"]),
        to_status=to_status,
        actor=str(data.get("reviewer_identity") or data.get("reviewer") or "human").strip(),
        original_response=str(current["original_response"]),
        corrected_response=corrected_response,
        reason=reason,
        error_tags=tags or [],
    )


def _save_review_conn(
    conn: sqlite3.Connection, review_id: int, data: dict[str, Any], db_path: Path | str
) -> dict[str, Any]:
    status = _required(data, "review_status").upper()
    if status not in FINAL_REVIEW_STATUSES:
        raise ValidationError("Invalid final review status")
    corrected = data.get("corrected_response")
    if status == "APPROVED":
        corrected = None
    elif corrected is None or not str(corrected).strip():
        raise ValidationError("The complete corrected response is required")
    current = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
    if not current:
        raise ValidationError("Review not found")
    _check_review_revision(current, data)
    # SEC-03: validate lifecycle transition before committing the UPDATE; without this
    # check _record_review_event silently returns when review_events table is absent,
    # allowing DELETED/IGNORED reviews to be approved without restoration.
    try:
        validate_transition(current["review_status"], status, corrected, None)
    except LifecycleError as exc:
        raise ValidationError(str(exc)) from exc
    saved_tags = [row[0] for row in conn.execute("SELECT tag FROM review_tags WHERE review_id=?", (review_id,))]
    raw_tags = data.get("tags", saved_tags)
    if not isinstance(raw_tags, list) or any(not isinstance(tag, str) for tag in raw_tags):
        raise ValidationError("Review tags must be a list of strings")
    tags = list(dict.fromkeys(raw_tags))
    invalid_tags = set(tags) - ERROR_TAGS
    if invalid_tags:
        raise ValidationError(f"Invalid tags: {', '.join(sorted(invalid_tags))}")
    flags = {}
    for key in ("training_eligible", "evaluation_only", "exclude_from_training",
                "contains_sensitive_data", "contains_personal_data", "needs_fact_check"):
        value = data.get(key, current[key])
        if not (type(value) is bool or type(value) is int and value in (0, 1)):
            raise ValidationError("Review flags must be booleans")
        flags[key] = int(value)
    training_eligible = flags["training_eligible"]
    evaluation_only = flags["evaluation_only"]
    if ((training_eligible or evaluation_only) and
        _review_collection_context(conn, current['message_id']).get('context_complete') is False):
        raise ValidationError(INCOMPLETE_CONTEXT_WARNING)
    exclude = flags["exclude_from_training"]
    if any(value for key, value in flags.items() if key != "training_eligible"):
        training_eligible = 0
    reviewer = _reviewer({"reviewer": current["reviewer"], **data})
    now = _review_revision_time(current)
    conn.execute(
                """
                UPDATE reviews SET review_status = ?, corrected_response = ?, review_notes = ?, reviewer = ?,
                    training_eligible = ?, exclude_from_training = ?, evaluation_only = ?,
                    contains_sensitive_data = ?, contains_personal_data = ?, needs_fact_check = ?,
                    ignored_at = NULL, ignored_reason = ?, deleted_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    corrected,
                    data.get("review_notes", current["review_notes"]),
                    reviewer,
                    training_eligible,
                    exclude,
                    evaluation_only,
                    flags["contains_sensitive_data"],
                    flags["contains_personal_data"],
                    flags["needs_fact_check"],
                    current["ignored_reason"],
                    now,
                    review_id,
                ),
            )
    conn.execute("DELETE FROM review_tags WHERE review_id = ?", (review_id,))
    conn.executemany(
        "INSERT INTO review_tags(review_id, tag) VALUES (?, ?)", [(review_id, tag) for tag in tags]
    )
    _record_review_event(conn, current, status, data, corrected_response=corrected, tags=tags)
    return get_review(review_id, db_path, conn=conn)


def approve_review(review_id: int, data: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    payload = {**data, "review_status": "APPROVED"}
    return save_review(review_id, payload, db_path)


def correct_review(review_id: int, data: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    status = _required(data, "review_status").upper()
    if status not in CORRECTION_REVIEW_STATUSES:
        raise ValidationError("Invalid correction type")
    payload = {**data, "review_status": status}
    return save_review(review_id, payload, db_path)


def ignore_review(review_id: int, data: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        with transaction(conn):
            current = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
            if not current:
                raise ValidationError("Review not found")
            now = utc_now()
            conn.execute(
                """
                UPDATE reviews SET review_status = 'IGNORED', training_eligible = 0,
                    ignored_at = ?, ignored_reason = ?, deleted_at = NULL, reviewer=?, updated_at = ?
                WHERE id = ?
                """,
                (now, str(data.get("ignored_reason") or "").strip() or None, _reviewer(data), now, review_id),
            )
            _record_review_event(conn, current, "IGNORED", data, reason=str(data.get("ignored_reason") or "Exclude from training"))
            return get_review(review_id, db_path, conn=conn)
    finally:
        conn.close()


def delete_review(review_id: int, data: dict[str, Any] | None = None, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        with transaction(conn):
            current = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
            if not current:
                raise ValidationError("Review not found")
            now = utc_now()
            conn.execute(
                """
                UPDATE reviews SET review_status = 'DELETED', training_eligible = 0,
                    ignored_at = NULL, ignored_reason = NULL, deleted_at = ?, reviewer=?, updated_at = ?
                WHERE id = ?
                """,
                (now, _reviewer(data or {}), now, review_id),
            )
            _record_review_event(conn, current, "DELETED", data or {}, reason=str((data or {}).get("reason") or "Soft delete"))
            return get_review(review_id, db_path, conn=conn)
    finally:
        conn.close()


def exclude_review(review_id: int, data: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    reason = _required(data, "reason")
    return ignore_review(review_id, {**data, "ignored_reason": reason}, db_path)


def _check_review_revision(current: sqlite3.Row, data: dict[str, Any]) -> None:
    if "expected_updated_at" in data and data["expected_updated_at"] != current["updated_at"]:
        raise ValidationError("The review changed after it was loaded; reload before saving")


def _review_revision_time(current: sqlite3.Row) -> str:
    now = datetime.fromisoformat(utc_now().replace("Z", "+00:00"))
    try:
        previous = datetime.fromisoformat(current["updated_at"].replace("Z", "+00:00"))
    except ValueError:
        # Legacy imported rows may have non-ISO timestamps; do not rewrite them
        # until an explicit action updates that row.
        previous = None
    if previous is not None:
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=timezone.utc)
        now = max(now, previous + timedelta(microseconds=1))
    return now.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _restore_review_conn(
    conn: sqlite3.Connection, review_id: int, data: dict[str, Any], db_path: Path | str
) -> dict[str, Any]:
    reason = _required(data, "reason")
    current = conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
    if not current:
        raise ValidationError("Review not found")
    _check_review_revision(current, data)
    if current["review_status"] not in {"IGNORED", "DELETED"}:
        raise ValidationError("Only excluded or deleted reviews can be restored")
    conn.execute(
        "UPDATE reviews SET review_status='PENDING',training_eligible=0,ignored_at=NULL,"
        "ignored_reason=?,deleted_at=NULL,reviewer=?,updated_at=? WHERE id=?",
        (reason, _reviewer({"reviewer": current["reviewer"], **data}), _review_revision_time(current), review_id),
    )
    tags = [row[0] for row in conn.execute("SELECT tag FROM review_tags WHERE review_id=?", (review_id,))]
    _record_review_event(conn, current, "PENDING", data, reason=reason,
                         corrected_response=current["corrected_response"], tags=tags)
    return get_review(review_id, db_path, conn=conn)


def restore_review(review_id: int, data: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        with transaction(conn):
            return _restore_review_conn(conn, review_id, data, db_path)
    finally:
        conn.close()


def bulk_review_actions(data: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    raw_ids = data.get("review_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValidationError("Select at least one review")
    try:
        review_ids = list(dict.fromkeys(int(value) for value in raw_ids))
    except (TypeError, ValueError):
        raise ValidationError("Invalid review identifiers") from None
    if len(review_ids) > 500:
        raise ValidationError("Bulk actions are limited to 500 reviews")
    action = _required(data, "action").lower()
    if action not in {"approve", "correct", "exclude", "restore"}:
        raise ValidationError("Invalid bulk review action")
    revisions = data.get("expected_updated_at_by_id")
    if revisions is not None:
        if not isinstance(revisions, dict) or any(
            not isinstance(revisions.get(str(review_id)), str) or not revisions[str(review_id)]
            for review_id in review_ids
        ):
            raise ValidationError("A saved revision is required for every selected review")
    conn = connect(db_path)
    results: list[dict[str, Any]] = []
    try:
        with transaction(conn):
            for review_id in review_ids:
                item_data = {**data}
                if revisions is not None:
                    item_data["expected_updated_at"] = revisions[str(review_id)]
                if action == "approve":
                    results.append(_save_review_conn(conn, review_id, {**item_data, "review_status": "APPROVED"}, db_path))
                elif action == "correct":
                    results.append(_save_review_conn(conn, review_id, item_data, db_path))
                elif action == "exclude":
                    reason = _required(data, "reason")
                    current = conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
                    if not current:
                        raise ValidationError("Review not found")
                    _check_review_revision(current, item_data)
                    now = _review_revision_time(current)
                    conn.execute("UPDATE reviews SET review_status='IGNORED',training_eligible=0,ignored_at=?,ignored_reason=?,deleted_at=NULL,reviewer=?,updated_at=? WHERE id=?", (now, reason, _reviewer(data), now, review_id))
                    _record_review_event(conn, current, "IGNORED", data, reason=reason)
                    results.append(get_review(review_id, db_path, conn=conn))
                else:
                    results.append(_restore_review_conn(conn, review_id, item_data, db_path))
        return {"action": action, "count": len(results), "items": results}
    finally:
        conn.close()


def get_review(
    review_id: int, db_path: Path | str = DB_PATH, conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT r.*, m.conversation_id, m.turn_index, c.title AS conversation_title,
                   c.provider, c.model_name, c.channel, c.demo
            FROM reviews r JOIN messages m ON m.id = r.message_id
            JOIN conversations c ON c.id = m.conversation_id WHERE r.id = ?
            """,
            (review_id,),
        ).fetchone()
        if not row:
            raise ValidationError("Review not found")
        item = dict(row)
        item["tags"] = [x[0] for x in conn.execute("SELECT tag FROM review_tags WHERE review_id = ?", (review_id,))]
        item["context"] = _message_context(conn, row["message_id"])
        item.update(_review_collection_context(conn, row["message_id"]))
        return item
    finally:
        if own_conn:
            conn.close()


def _conversation_filter(search: str, model: str, channel: str) -> tuple[str, list[Any]]:
    params: list[Any] = []
    clauses = ["1=1"]
    if search:
        clauses.append("(c.title LIKE ? OR c.external_conversation_id LIKE ? OR EXISTS (SELECT 1 FROM messages sm WHERE sm.conversation_id = c.id AND sm.content LIKE ?))")
        q = f"%{search}%"
        params.extend([q, q, q])
    if model:
        clauses.append("c.model_name = ?")
        params.append(model)
    if channel:
        clauses.append("c.channel = ?")
        params.append(channel)
    return " AND ".join(clauses), params


def _conversation_rows(conn: sqlite3.Connection, where: str, params: list[Any], page: tuple[int, int] | None) -> list[dict[str, Any]]:
    window = " LIMIT ? OFFSET ?" if page else ""
    rows = conn.execute(
        f"""
        SELECT c.*, COUNT(DISTINCT m.id) AS message_count,
               SUM(CASE WHEN r.review_status = 'PENDING' THEN 1 ELSE 0 END) AS pending_count
        FROM conversations c
        LEFT JOIN messages m ON m.conversation_id = c.id
        LEFT JOIN reviews r ON r.message_id = m.id
        WHERE {where}
        GROUP BY c.id ORDER BY c.updated_at DESC, c.id DESC{window}
        """,
        [*params, *(page or ())],
    ).fetchall()
    return [dict(row) for row in rows]


def list_conversations(
    db_path: Path | str = DB_PATH, search: str = "", model: str = "", channel: str = ""
) -> list[dict[str, Any]]:
    conn = connect(db_path)
    try:
        where, params = _conversation_filter(search, model, channel)
        return _conversation_rows(conn, where, params, None)
    finally:
        conn.close()


def conversations_page(query: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    limit, offset = page_request(query)
    conn = connect(db_path)
    try:
        where, params = _conversation_filter(query.get("search", ""), query.get("model", ""), query.get("channel", ""))
        total = conn.execute(f"SELECT COUNT(*) FROM conversations c WHERE {where}", params).fetchone()[0]
        items = _conversation_rows(conn, where, params, (limit, offset))
        return {"items": items, "page": page_info(total, limit, offset, len(items))}
    finally:
        conn.close()


def get_conversation(conversation_id: int, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        conversation = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not conversation:
            raise ValidationError("Conversation not found")
        messages = conn.execute(
            """
            SELECT m.*, r.id AS review_id, r.review_status, r.corrected_response,
                   r.training_eligible, r.evaluation_only, r.exclude_from_training
            FROM messages m LEFT JOIN reviews r ON r.message_id = m.id
            WHERE m.conversation_id = ? ORDER BY m.turn_index
            """,
            (conversation_id,),
        ).fetchall()
        return {"conversation": dict(conversation), "messages": [dict(row) for row in messages]}
    finally:
        conn.close()


def _reviewed_filter(filters: dict[str, str]) -> tuple[str, list[Any]]:
    requested_status = str(filters.get("review_status") or "").upper()
    params: list[Any] = []
    if requested_status:
        if requested_status not in REVIEW_STATUSES:
            raise ValidationError("Invalid review status")
        clauses = ["r.review_status = ?"]
        params.append(requested_status)
    else:
        placeholders = ",".join("?" for _ in TRAINING_REVIEW_STATUSES)
        clauses = [f"r.review_status IN ({placeholders})"]
        params.extend(sorted(TRAINING_REVIEW_STATUSES))
    mapping = {
        "model": "c.model_name",
        "provider": "c.provider",
        "channel": "c.channel",
    }
    for key, column in mapping.items():
        if filters.get(key):
            clauses.append(f"{column} = ?")
            params.append(filters[key])
    for key in ("training_eligible", "evaluation_only"):
        if filters.get(key) in {"0", "1"}:
            clauses.append(f"r.{key} = ?")
            params.append(int(filters[key]))
    if filters.get("tag"):
        clauses.append("EXISTS (SELECT 1 FROM review_tags rt WHERE rt.review_id = r.id AND rt.tag = ?)")
        params.append(filters["tag"])
    if filters.get("date_from"):
        clauses.append("r.updated_at >= ?")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        clauses.append("r.updated_at <= ?")
        params.append(filters["date_to"] + "T23:59:59Z")
    if filters.get("search"):
        clauses.append("(r.original_response LIKE ? OR r.corrected_response LIKE ? OR r.review_notes LIKE ? OR c.title LIKE ?)")
        q = f"%{filters['search']}%"
        params.extend([q, q, q, q])
    return " AND ".join(clauses), params


_REVIEWED_FROM = """FROM reviews r JOIN messages m ON m.id = r.message_id
            JOIN conversations c ON c.id = m.conversation_id"""


def _reviewed_rows(conn: sqlite3.Connection, where: str, params: list[Any], limit: int, offset: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT r.*, c.title AS conversation_title, c.model_name, c.provider, c.channel, c.demo,
               m.turn_index, GROUP_CONCAT(rt.tag) AS tags_csv
        {_REVIEWED_FROM}
        LEFT JOIN review_tags rt ON rt.review_id = r.id
        WHERE {where}
        GROUP BY r.id ORDER BY r.updated_at DESC, r.id DESC LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["tags"] = item.pop("tags_csv").split(",") if item.get("tags_csv") else []
        result.append(item)
    return result


def list_reviewed(filters: dict[str, str], db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    # Core profile contract: a plain list of at most 500 items. The full app uses reviewed_page.
    where, params = _reviewed_filter(filters)
    conn = connect(db_path)
    try:
        return _reviewed_rows(conn, where, params, PAGE_MAX_LIMIT, 0)
    finally:
        conn.close()


def reviewed_page(filters: dict[str, str], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    limit, offset = page_request(filters)
    where, params = _reviewed_filter(filters)
    conn = connect(db_path)
    try:
        total = conn.execute(f"SELECT COUNT(*) {_REVIEWED_FROM} WHERE {where}", params).fetchone()[0]
        items = _reviewed_rows(conn, where, params, limit, offset)
        return {"items": items, "page": page_info(total, limit, offset, len(items))}
    finally:
        conn.close()


def _manual_snapshot(row: sqlite3.Row | dict[str, Any], item_type: str) -> dict[str, Any]:
    item = dict(row)
    item["item_type"] = item_type
    if item_type == "sft":
        item["messages"] = json_loads(item.pop("messages_json", None), [])
    elif item_type == "dpo":
        item["prompt_context"] = json_loads(item.pop("prompt_context_json", None), [])
    item["metadata"] = json_loads(item.pop("metadata_json", None), {})
    item["training_eligible_effective"] = bool(
        item.get("training_eligible")
        and not item.get("archived")
        and not item.get("exclude_from_training")
        and not item.get("evaluation_only")
        and not item.get("ignored_at")
        and not item.get("deleted_at")
    )
    return item


def _manual_preview(item: dict[str, Any]) -> str:
    if item["item_type"] == "sft":
        return " · ".join(str(turn.get("content") or "") for turn in item.get("messages", []))
    if item["item_type"] == "direct":
        return str(item.get("text") or "")
    context = " · ".join(str(turn.get("content") or "") for turn in item.get("prompt_context", []))
    return " · ".join(part for part in (context, item.get("preferred_response")) if part)


def _manual_export_versions(conn: sqlite3.Connection, item_type: str, item_id: int) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            """
            SELECT d.version FROM manual_data_export_history h
            JOIN dataset_versions d ON d.id = h.dataset_version_id
            WHERE h.item_type = ? AND h.item_id = ? ORDER BY d.id
            """,
            (item_type, item_id),
        )
    ]


def _manual_item(
    conn: sqlite3.Connection, item_type: str, item_id: int, include_deleted: bool = False
) -> dict[str, Any]:
    table = MANUAL_TABLES.get(item_type)
    if not table:
        raise ValidationError("Invalid manual data type")
    lifecycle_clause = "" if include_deleted else " AND deleted_at IS NULL"
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?{lifecycle_clause}", (item_id,)).fetchone()
    if not row:
        raise ValidationError("Item not found")
    item = _manual_snapshot(row, item_type)
    item["preview"] = _manual_preview(item)
    item["exported_versions"] = _manual_export_versions(conn, item_type, item_id)
    item["exported_before"] = bool(item["exported_versions"])
    return item


def initialize_manual_versions(db_path: Path | str = DB_PATH) -> int:
    """Create immutable v1 snapshots for legacy rows after migration 003."""
    conn = connect(db_path)
    inserted = 0
    try:
        with transaction(conn):
            for item_type, table in MANUAL_TABLES.items():
                for row in conn.execute(f"SELECT * FROM {table} ORDER BY id"):
                    exists = conn.execute(
                        "SELECT 1 FROM manual_data_versions WHERE item_type = ? AND item_id = ? AND version_number = ?",
                        (item_type, row["id"], row["version_number"]),
                    ).fetchone()
                    if exists:
                        continue
                    conn.execute(
                        """
                        INSERT INTO manual_data_versions(
                            item_type, item_id, version_number, snapshot_json,
                            changed_fields_json, change_notes, changed_by, created_at
                        ) VALUES (?, ?, ?, ?, '[]', ?, 'system', ?)
                        """,
                        (
                            item_type,
                            row["id"],
                            row["version_number"],
                            json_dumps(_manual_snapshot(row, item_type)),
                            "Create a baseline version for the existing record",
                            row["updated_at"] or row["created_at"],
                        ),
                    )
                    inserted += 1
        return inserted
    finally:
        conn.close()


def sync_manual_export_history(db_path: Path | str = DB_PATH) -> int:
    """Index manual IDs present in immutable export JSONL files without modifying them."""
    conn = connect(db_path)
    inserted = 0
    export_files = (
        "sft.jsonl",
        "multi_turn.jsonl",
        "direct_language.jsonl",
        "preference_pairs.jsonl",
        "evaluation_holdout.jsonl",
    )
    try:
        with transaction(conn):
            for version in conn.execute("SELECT id, version, created_at, export_path, manifest_json FROM dataset_versions ORDER BY id"):
                export_dir = Path(version["export_path"])
                manifest = json_loads(version["manifest_json"], {})
                include_demo = bool((manifest.get("filters_used") or {}).get("include_demo"))
                reconstructed: dict[str, list[dict[str, Any]]] | None = None
                for filename in export_files:
                    path = export_dir / filename
                    readable = True
                    try:
                        if path.is_file():
                            lines = path.read_text(encoding="utf-8").splitlines()
                        else:
                            readable = False
                            lines = []
                    except OSError:
                        readable = False
                        lines = []
                    exported_items: list[dict[str, Any]] = []
                    if readable:
                        for line in lines:
                            try:
                                exported_items.append(json.loads(line))
                            except (json.JSONDecodeError, TypeError):
                                continue
                    else:
                        if reconstructed is None:
                            review_ids_as_of = {
                                f"review:{row[0]}"
                                for row in conn.execute(
                                    "SELECT id FROM reviews WHERE created_at <= ?", (version["created_at"],)
                                )
                            }
                            reviews = [
                                item for item in _review_training_records(conn, include_demo)
                                if item.get("id") in review_ids_as_of
                            ]
                            manual_sft = [
                                item for item in _manual_records(conn, "manual_sft_items", include_demo)
                                if str(item.get("created_at") or "") <= version["created_at"]
                            ]
                            direct_items = [
                                item for item in _manual_records(conn, "direct_language_texts", include_demo)
                                if str(item.get("created_at") or "") <= version["created_at"]
                            ]
                            preference_items = [
                                item for item in _manual_records(conn, "preference_pairs", include_demo)
                                if str(item.get("created_at") or "") <= version["created_at"]
                            ]
                            all_sft = reviews + manual_sft
                            reconstructed = {
                                "sft.jsonl": [item for item in all_sft if len(item.get("messages", [])) <= 2],
                                "multi_turn.jsonl": [item for item in all_sft if len(item.get("messages", [])) > 2],
                                "direct_language.jsonl": direct_items,
                                "preference_pairs.jsonl": preference_items,
                                "evaluation_holdout.jsonl": (
                                    _review_training_records(conn, include_demo, evaluation=True)
                                    + _manual_records(conn, "manual_sft_items", include_demo, evaluation=True)
                                    + _manual_records(conn, "direct_language_texts", include_demo, evaluation=True)
                                    + _manual_records(conn, "preference_pairs", include_demo, evaluation=True)
                                ),
                            }
                        candidate_items = reconstructed.get(filename, [])
                        expected = (manifest.get("sha256") or {}).get(filename)
                        variants = [candidate_items]
                        legacy_items = []
                        for item in candidate_items:
                            legacy = dict(item)
                            if str(legacy.get("id") or "").split(":", 1)[0] in MANUAL_TYPES_BY_TABLE:
                                for key in ("version_number", "archived", "parent_item_id", "updated_at"):
                                    legacy.pop(key, None)
                                if str(legacy["id"]).startswith(("manual_sft_items:", "preference_pairs:")):
                                    legacy.pop("source", None)
                                    legacy.pop("source_type", None)
                            legacy_items.append(legacy)
                        variants.append(legacy_items)
                        for variant in variants:
                            candidate_bytes = b"".join(
                                (json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                                for item in variant
                            )
                            if expected and hashlib.sha256(candidate_bytes).hexdigest() == expected:
                                exported_items = candidate_items
                                break
                    for exported in exported_items:
                        exported_id = str(exported.get("id") or "")
                        if ":" not in exported_id:
                            continue
                        table, raw_id = exported_id.split(":", 1)
                        item_type = MANUAL_TYPES_BY_TABLE.get(table)
                        if not item_type or not raw_id.isdigit():
                            continue
                        cursor = conn.execute(
                            """
                            INSERT OR IGNORE INTO manual_data_export_history(
                                item_type, item_id, dataset_version_id, exported_at
                            ) VALUES (?, ?, ?, ?)
                            """,
                            (item_type, int(raw_id), version["id"], version["created_at"]),
                        )
                        inserted += cursor.rowcount
                review_count = sum((manifest.get("review_status_counts") or {}).values())
                expected_manual = int(manifest.get("record_count") or 0) - int(review_count)
                indexed_manual = conn.execute(
                    "SELECT COUNT(*) FROM manual_data_export_history WHERE dataset_version_id = ?",
                    (version["id"],),
                ).fetchone()[0]
                if expected_manual > indexed_manual and not int(manifest.get("evaluation_only_count") or 0):
                    languages = set(manifest.get("language_layers") or [])
                    domains = set(manifest.get("domains") or [])
                    candidates: list[tuple[str, int]] = []
                    for candidate_type, table in MANUAL_TABLES.items():
                        for row in conn.execute(
                            f"SELECT id, created_at, language_layer, domain FROM {table} WHERE created_at <= ?",
                            (version["created_at"],),
                        ):
                            already = conn.execute(
                                """
                                SELECT 1 FROM manual_data_export_history
                                WHERE item_type = ? AND item_id = ? AND dataset_version_id = ?
                                """,
                                (candidate_type, row["id"], version["id"]),
                            ).fetchone()
                            if already:
                                continue
                            if languages and row["language_layer"] not in languages:
                                continue
                            if domains and row["domain"] not in domains:
                                continue
                            candidates.append((candidate_type, row["id"]))
                    missing = expected_manual - indexed_manual
                    if len(candidates) == missing:
                        for candidate_type, candidate_id in candidates:
                            cursor = conn.execute(
                                """
                                INSERT OR IGNORE INTO manual_data_export_history(
                                    item_type, item_id, dataset_version_id, exported_at
                                ) VALUES (?, ?, ?, ?)
                                """,
                                (candidate_type, candidate_id, version["id"], version["created_at"]),
                            )
                            inserted += cursor.rowcount
        return inserted
    finally:
        conn.close()


def list_manual_data(filters: dict[str, str], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    limit, offset = page_request(filters)
    conn = connect(db_path)
    try:
        all_items: list[dict[str, Any]] = []
        for item_type, table in MANUAL_TABLES.items():
            for row in conn.execute(f"SELECT * FROM {table}"):
                item = _manual_snapshot(row, item_type)
                item["preview"] = _manual_preview(item)
                item["exported_versions"] = _manual_export_versions(conn, item_type, row["id"])
                item["exported_before"] = bool(item["exported_versions"])
                all_items.append(item)

        summary = {
            "total": len(all_items),
            "sft": sum(item["item_type"] == "sft" for item in all_items),
            "direct": sum(item["item_type"] == "direct" for item in all_items),
            "dpo": sum(item["item_type"] == "dpo" for item in all_items),
            "eligible": sum(item["training_eligible_effective"] for item in all_items),
            "ineligible": sum(not item["training_eligible_effective"] for item in all_items),
            "archived": sum(bool(item.get("archived")) for item in all_items),
            "excluded": sum(bool(item.get("exclude_from_training")) for item in all_items),
            "ignored": sum(bool(item.get("ignored_at")) and not item.get("deleted_at") for item in all_items),
            "deleted": sum(bool(item.get("deleted_at")) for item in all_items),
        }

        item_type = filters.get("type", "")
        if item_type in MANUAL_TABLES:
            all_items = [item for item in all_items if item["item_type"] == item_type]
        status = filters.get("status", "")
        if status == "ignored":
            all_items = [item for item in all_items if item.get("ignored_at") and not item.get("deleted_at")]
        elif status == "deleted":
            all_items = [item for item in all_items if item.get("deleted_at")]
        else:
            all_items = [item for item in all_items if not item.get("ignored_at") and not item.get("deleted_at")]
        show_archived = filters.get("show_archived") == "1" or status == "archived"
        if not show_archived:
            all_items = [item for item in all_items if not item.get("archived")]
        if status == "eligible":
            all_items = [item for item in all_items if item["training_eligible_effective"]]
        elif status == "ineligible":
            all_items = [item for item in all_items if not item["training_eligible_effective"]]
        elif status == "archived":
            all_items = [item for item in all_items if item.get("archived")]
        elif status == "excluded":
            all_items = [item for item in all_items if item.get("exclude_from_training")]
        for key in ("language_layer", "source", "origin", "domain"):
            if filters.get(key):
                needle = filters[key].casefold()
                all_items = [item for item in all_items if needle in str(item.get(key) or "").casefold()]
        if filters.get("date_from"):
            all_items = [item for item in all_items if str(item.get("created_at") or "") >= filters["date_from"]]
        if filters.get("date_to"):
            all_items = [item for item in all_items if str(item.get("created_at") or "") <= filters["date_to"] + "T23:59:59Z"]
        if filters.get("search"):
            needle = filters["search"].casefold()
            all_items = [
                item for item in all_items
                if needle in " ".join(
                    str(item.get(key) or "") for key in ("preview", "notes", "source", "origin", "domain")
                ).casefold()
            ]

        sort = filters.get("sort", "newest")
        reverse = sort not in {"oldest", "type", "domain", "language_layer"}
        key_functions = {
            "newest": lambda item: item.get("created_at") or "",
            "oldest": lambda item: item.get("created_at") or "",
            "updated": lambda item: item.get("updated_at") or item.get("created_at") or "",
            "type": lambda item: item.get("item_type") or "",
            "domain": lambda item: item.get("domain") or "",
            "language_layer": lambda item: item.get("language_layer") or "",
            "eligible": lambda item: int(item.get("training_eligible_effective", False)),
        }
        all_items.sort(key=key_functions.get(sort, key_functions["newest"]), reverse=reverse)
        facets = {
            key: sorted({str(item.get(key)) for item in all_items if item.get(key)})
            for key in ("source", "origin", "domain")
        }
        items = all_items[offset:offset + limit]
        return {"items": items, "summary": summary, "facets": facets,
                "page": page_info(len(all_items), limit, offset, len(items))}
    finally:
        conn.close()


def get_manual_data(item_type: str, item_id: int, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        return _manual_item(conn, item_type, item_id)
    finally:
        conn.close()


def list_manual_versions(item_type: str, item_id: int, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    conn = connect(db_path)
    try:
        _manual_item(conn, item_type, item_id)
        versions = []
        for row in conn.execute(
            "SELECT * FROM manual_data_versions WHERE item_type = ? AND item_id = ? ORDER BY version_number DESC",
            (item_type, item_id),
        ):
            item = dict(row)
            item["snapshot"] = json_loads(item.pop("snapshot_json"), {})
            item["changed_fields"] = json_loads(item.pop("changed_fields_json"), [])
            versions.append(item)
        return versions
    finally:
        conn.close()


def _validate_manual_payload(
    item_type: str, data: dict[str, Any], current: dict[str, Any], allow_lifecycle: bool = False
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    common = {
        "language_layer", "domain", "source", "source_type", "origin", "notes",
        "training_eligible", "exclude_from_training", "evaluation_only",
        "contains_sensitive_data", "contains_personal_data", "archived",
    }
    if allow_lifecycle:
        common |= {"ignored_at", "ignored_reason", "deleted_at"}
    specific = {
        "sft": {"messages"},
        "direct": {"text"},
        "dpo": {"prompt_context", "rejected_response", "preferred_response"},
    }[item_type]
    for key in common | specific:
        if key in data:
            payload[key] = data[key]
    layer = payload.get("language_layer", current.get("language_layer"))
    if layer not in LANGUAGE_LAYERS:
        raise ValidationError("Invalid language layer")
    origin = payload.get("origin", current.get("origin"))
    if origin not in ORIGINS:
        raise ValidationError("Invalid origin")
    for key in ("origin", "source_type"):
        if key in payload and not str(payload[key] or "").strip():
            raise ValidationError(f"Original source data cannot be cleared: {key}")
    if "source" in payload and current.get("source") and not str(payload["source"] or "").strip():
        raise ValidationError("Original source data cannot be cleared: source")
    if item_type == "sft":
        messages = payload.get("messages", current.get("messages"))
        if not isinstance(messages, list) or len(messages) < 2:
            raise ValidationError("Add at least one user message and one assistant message")
        if any(turn.get("role") not in {"system", "user", "assistant"} or not str(turn.get("content") or "").strip() for turn in messages):
            raise ValidationError("All conversation turns must be valid and nonempty")
        payload["messages_json"] = json_dumps(messages)
        payload.pop("messages", None)
    elif item_type == "direct":
        text = str(payload.get("text", current.get("text")) or "").strip()
        if not text:
            raise ValidationError("Text cannot be empty")
        payload["text"] = text
        source_type = payload.get("source_type", current.get("source_type"))
        if source_type not in {"human_written", "human_corrected", "synthetic_reviewed", "external_licensed"}:
            raise ValidationError("Invalid source type")
    else:
        context = payload.get("prompt_context", current.get("prompt_context"))
        if isinstance(context, str):
            context = [{"role": "user", "content": context.strip()}]
        if not isinstance(context, list) or not context or not any(str(turn.get("content") or "").strip() for turn in context):
            raise ValidationError("Prompt / Context is required")
        rejected = str(payload.get("rejected_response", current.get("rejected_response")) or "").strip()
        preferred = str(payload.get("preferred_response", current.get("preferred_response")) or "").strip()
        if not rejected or not preferred:
            raise ValidationError("The rejected and preferred responses are required")
        if rejected == preferred:
            raise ValidationError("The rejected response must differ from the preferred response")
        payload["prompt_context_json"] = json_dumps(context)
        payload.pop("prompt_context", None)
        payload["rejected_response"] = rejected
        payload["preferred_response"] = preferred
    for key in ("training_eligible", "exclude_from_training", "evaluation_only", "contains_sensitive_data", "contains_personal_data", "archived"):
        if key in payload:
            payload[key] = _bool(payload[key])
    return payload


def _update_manual_data_conn(
    conn: sqlite3.Connection,
    item_type: str,
    item_id: int,
    data: dict[str, Any],
    *,
    include_deleted_result: bool = False,
    allow_lifecycle: bool = False,
) -> dict[str, Any]:
    table = MANUAL_TABLES.get(item_type)
    if not table:
        raise ValidationError("Invalid manual data type")
    current = _manual_item(conn, item_type, item_id)
    payload = _validate_manual_payload(item_type, data, current, allow_lifecycle=allow_lifecycle)
    changed_fields = []
    for key, value in payload.items():
        old_key = key.removesuffix("_json")
        old_value = current.get(old_key)
        comparison = json_loads(value, []) if key.endswith("_json") else value
        if old_value != comparison:
            changed_fields.append(old_key)
    if not changed_fields:
        return current
    version = int(current.get("version_number") or 1) + 1
    payload["version_number"] = version
    payload["updated_at"] = utc_now()
    assignments = ", ".join(f"{key} = ?" for key in payload)
    conn.execute(
        f"UPDATE {table} SET {assignments} WHERE id = ?",
        [*payload.values(), item_id],
    )
    updated_row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
    snapshot = _manual_snapshot(updated_row, item_type)
    changed_by = data.get("changed_by") or "human"
    if changed_by not in {"human", "system"}:
        raise ValidationError("Invalid changed_by value")
    conn.execute(
        """
        INSERT INTO manual_data_versions(
            item_type, item_id, version_number, snapshot_json, changed_fields_json,
            change_notes, changed_by, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item_type, item_id, version, json_dumps(snapshot), json_dumps(changed_fields),
            str(data.get("change_notes") or "Manual edit").strip(), changed_by, payload["updated_at"],
        ),
    )
    return _manual_item(conn, item_type, item_id, include_deleted=include_deleted_result)


def update_manual_data(
    item_type: str,
    item_id: int,
    data: dict[str, Any],
    db_path: Path | str = DB_PATH,
    *,
    include_deleted_result: bool = False,
    allow_lifecycle: bool = False,
) -> dict[str, Any]:
    if not MANUAL_TABLES.get(item_type):
        raise ValidationError("Invalid manual data type")
    conn = connect(db_path)
    try:
        with transaction(conn):
            return _update_manual_data_conn(
                conn, item_type, item_id, data,
                include_deleted_result=include_deleted_result,
                allow_lifecycle=allow_lifecycle,
            )
    finally:
        conn.close()


def clone_manual_data(item_type: str, item_id: int, data: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        current = _manual_item(conn, item_type, item_id)
    finally:
        conn.close()
    clone = dict(current)
    clone.update(data)
    clone["parent_item_id"] = item_id
    clone["archived"] = False
    clone["change_notes"] = data.get("change_notes") or f"New copy of {item_type}:{item_id}"
    for key in ("id", "item_type", "created_at", "updated_at", "version_number", "preview", "exported_versions", "exported_before", "training_eligible_effective", "metadata", "ignored_at", "ignored_reason", "deleted_at"):
        clone.pop(key, None)
    if item_type == "sft":
        return add_manual_sft(clone, db_path)
    if item_type == "direct":
        return add_direct_text(clone, db_path)
    return add_preference_pair(clone, db_path)


def delete_manual_data(item_type: str, item_id: int, confirm_exported: bool = False, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    table = MANUAL_TABLES.get(item_type)
    if not table:
        raise ValidationError("Invalid manual data type")
    conn = connect(db_path)
    try:
        current = _manual_item(conn, item_type, item_id)
    finally:
        conn.close()
    if current["exported_before"] and not confirm_exported:
        raise ValidationError("This record was already included in a previous dataset version.")
    deleted_at = utc_now()
    updated = update_manual_data(
        item_type,
        item_id,
        {
            "deleted_at": deleted_at,
            "ignored_at": None,
            "ignored_reason": None,
            "training_eligible": False,
            "exclude_from_training": True,
            "change_notes": "Soft delete record",
        },
        db_path,
        include_deleted_result=True,
        allow_lifecycle=True,
    )
    return {"deleted": True, "deleted_at": updated["deleted_at"], "exported_versions": current["exported_versions"]}


def ignore_manual_data(
    item_type: str, item_id: int, data: dict[str, Any], db_path: Path | str = DB_PATH
) -> dict[str, Any]:
    return update_manual_data(
        item_type,
        item_id,
        {
            "ignored_at": utc_now(),
            "ignored_reason": str(data.get("ignored_reason") or "").strip() or None,
            "deleted_at": None,
            "training_eligible": False,
            "exclude_from_training": True,
            "change_notes": data.get("change_notes") or "Ignore record",
        },
        db_path,
        allow_lifecycle=True,
    )


def bulk_update_manual_data(data: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    items = data.get("items")
    action = data.get("action")
    actions = {
        "eligible": {"training_eligible": True},
        "ineligible": {"training_eligible": False},
        "archive": {"archived": True},
        "unarchive": {"archived": False},
        "exclude": {"exclude_from_training": True},
        "include": {"exclude_from_training": False},
    }
    if not isinstance(items, list) or not items or action not in actions:
        raise ValidationError("Invalid bulk action")
    # SEC-04: reject oversized batches explicitly — silent truncation at 500 hides data loss.
    if len(items) > 500:
        raise ValidationError(f"Batch too large: {len(items)} items exceed the 500-item limit")
    # SEC-04: validate all items before opening a transaction — reject the whole request
    # if any item is malformed; do not silently ignore bad entries.
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValidationError(f"Item at position {index} is not a dict")
        item_type = item.get("type")
        item_id = item.get("id")
        if item_type not in MANUAL_TABLES:
            raise ValidationError(f"Item at position {index} has invalid type {item_type!r}")
        try:
            int(item_id)
        except (TypeError, ValueError):
            raise ValidationError(f"Item at position {index} has invalid id {item_id!r}")
    updated = 0
    # SEC-04: wrap all item updates in one transaction so a failure on item N does not
    # leave items 1..N-1 already committed while the rest are not.
    conn = connect(db_path)
    try:
        with transaction(conn):
            for item in items:
                payload = {**actions[action], "change_notes": data.get("change_notes") or "Bulk edit"}
                _update_manual_data_conn(conn, str(item.get("type")), int(item.get("id")), payload)
                updated += 1
    finally:
        conn.close()
    return {"updated": updated}


def add_manual_sft(data: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    messages = data.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        raise ValidationError("Add at least one user message and one assistant message")
    for index, message in enumerate(messages):
        if message.get("role") not in {"system", "user", "assistant"} or not str(message.get("content", "")).strip():
            raise ValidationError(f"Invalid message at position {index + 1}")
    language_layer = data.get("language_layer") or "saudi_neutral"
    if language_layer not in LANGUAGE_LAYERS:
        raise ValidationError("Invalid language layer")
    return _insert_training_item("manual_sft_items", {**data, "messages_json": json_dumps(messages)}, db_path)


def add_direct_text(data: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    _required(data, "text")
    if data.get("language_layer") not in LANGUAGE_LAYERS:
        raise ValidationError("Invalid language layer")
    if data.get("source_type") not in {"human_written", "human_corrected", "synthetic_reviewed", "external_licensed"}:
        raise ValidationError("Invalid source type")
    return _insert_training_item("direct_language_texts", data, db_path)


def add_preference_pair(data: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    rejected = _required(data, "rejected_response")
    preferred = _required(data, "preferred_response")
    if rejected == preferred:
        raise ValidationError("The rejected response must differ from the preferred response")
    context = data.get("prompt_context")
    if not context:
        raise ValidationError("Prompt / Context is required")
    if isinstance(context, str):
        context = [{"role": "user", "content": context}]
    return _insert_training_item(
        "preference_pairs", {**data, "prompt_context_json": json_dumps(context)}, db_path
    )


def _insert_training_item(table: str, data: dict[str, Any], db_path: Path | str) -> dict[str, Any]:
    origin = data.get("origin") or "manual"
    if origin not in ORIGINS:
        raise ValidationError("Invalid origin")
    evaluation_only = _bool(data.get("evaluation_only"))
    exclude = _bool(data.get("exclude_from_training"))
    eligible = 0 if evaluation_only or exclude else _bool(data.get("training_eligible"))
    now = utc_now()
    common = {
        "language_layer": data.get("language_layer") or "saudi_neutral",
        "domain": data.get("domain"),
        "origin": origin,
        "notes": data.get("notes"),
        "training_eligible": eligible,
        "exclude_from_training": exclude,
        "evaluation_only": evaluation_only,
        "contains_sensitive_data": _bool(data.get("contains_sensitive_data")),
        "contains_personal_data": _bool(data.get("contains_personal_data")),
        "created_at": now,
        "metadata_json": json_dumps(redact_secrets(data.get("metadata") or {})),
        "demo": _bool(data.get("demo")),
        "version_number": 1,
        "archived": _bool(data.get("archived")),
        "parent_item_id": data.get("parent_item_id"),
        "updated_at": now,
    }
    table_specific: dict[str, list[str]] = {
        "manual_sft_items": ["messages_json", "source", "source_type"],
        "direct_language_texts": ["text", "source", "source_type"],
        "preference_pairs": ["prompt_context_json", "rejected_response", "preferred_response", "source", "source_type"],
    }
    payload = {**common, **{key: data.get(key) for key in table_specific[table]}}
    if table != "direct_language_texts":
        payload["source"] = payload.get("source") or "NajdiLab manual entry"
        payload["source_type"] = payload.get("source_type") or (
            "synthetic_reviewed" if origin == "synthetic_reviewed" else "human_written"
        )
    columns = list(payload)
    conn = connect(db_path)
    try:
        with transaction(conn):
            cursor = conn.execute(
                f"INSERT INTO {table}({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                [payload[column] for column in columns],
            )
            row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (cursor.lastrowid,)).fetchone()
            item_type = MANUAL_TYPES_BY_TABLE[table]
            snapshot = _manual_snapshot(row, item_type)
            conn.execute(
                """
                INSERT INTO manual_data_versions(
                    item_type, item_id, version_number, snapshot_json,
                    changed_fields_json, change_notes, changed_by, created_at
                ) VALUES (?, ?, 1, ?, '[]', ?, 'human', ?)
                """,
                (
                    item_type,
                    cursor.lastrowid,
                    json_dumps(snapshot),
                    str(data.get("change_notes") or "Create record").strip(),
                    now,
                ),
            )
            return dict(row)
    finally:
        conn.close()


def _review_training_records(conn: sqlite3.Connection, include_demo: bool, evaluation: bool = False) -> list[dict[str, Any]]:
    if evaluation:
        where = "r.evaluation_only = 1 AND r.exclude_from_training = 0"
    else:
        where = "r.training_eligible = 1 AND r.evaluation_only = 0 AND r.exclude_from_training = 0"
    allowed_statuses = sorted(TRAINING_REVIEW_STATUSES)
    placeholders = ",".join("?" for _ in allowed_statuses)
    rows = conn.execute(
        f"""
        SELECT r.*, m.turn_index, m.conversation_id, c.external_conversation_id, c.title,
               c.source, c.channel, c.provider, c.model_name, c.model_version, c.demo
        FROM reviews r JOIN messages m ON m.id = r.message_id
        JOIN conversations c ON c.id = m.conversation_id
        WHERE {where} AND r.review_status IN ({placeholders}) AND (? = 1 OR c.demo = 0)
        ORDER BY c.id, m.turn_index
        """,
        (*allowed_statuses, _bool(include_demo)),
    ).fetchall()
    records = []
    for row in rows:
        context = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? AND turn_index <= ? ORDER BY turn_index",
            (row["conversation_id"], row["turn_index"]),
        ).fetchall()
        messages = [dict(item) for item in context]
        messages[-1]["content"] = row["corrected_response"] or row["original_response"]
        records.append(
            {
                "id": f"review:{row['id']}",
                "conversation_id": row["external_conversation_id"],
                "messages": messages,
                "origin": "human_corrected" if row["corrected_response"] else "real_conversation",
                "review_status": row["review_status"],
                "contains_personal_data": bool(row["contains_personal_data"]),
                "contains_sensitive_data": bool(row["contains_sensitive_data"]),
                "provider": row["provider"],
                "model_name": row["model_name"],
                "model_version": row["model_version"],
                "channel": row["channel"],
                "demo": row["demo"],
                "tags": [x[0] for x in conn.execute("SELECT tag FROM review_tags WHERE review_id = ?", (row["id"],))],
                **_review_collection_context(conn, row['message_id']),
            }
        )
    return records


def _manual_records(conn: sqlite3.Connection, table: str, include_demo: bool, evaluation: bool = False) -> list[dict[str, Any]]:
    eligibility = "evaluation_only = 1" if evaluation else "training_eligible = 1 AND evaluation_only = 0"
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE {eligibility} AND archived = 0 AND exclude_from_training = 0 "
        "AND ignored_at IS NULL AND deleted_at IS NULL AND (? = 1 OR demo = 0) ORDER BY id",
        (_bool(include_demo),),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["id"] = f"{table}:{row['id']}"
        for key in ("messages_json", "prompt_context_json", "metadata_json"):
            if key in item:
                item[key.removesuffix("_json")] = json_loads(item.pop(key), [])
        result.append(item)
    return result


def training_dataset(db_path: Path | str = DB_PATH, include_demo: bool = False) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        reviews = _review_training_records(conn, include_demo)
        manual = _manual_records(conn, "manual_sft_items", include_demo)
        direct = _manual_records(conn, "direct_language_texts", include_demo)
        preference = _manual_records(conn, "preference_pairs", include_demo)
        return {
            "reviews": reviews,
            "manual_sft": manual,
            "direct_language": direct,
            "preference_pairs": preference,
            "stats": {
                "total_approved": sum(1 for item in reviews if item["review_status"] == "APPROVED"),
                "full_corrections": sum(1 for item in reviews if item["review_status"] == "FULL_CORRECTION"),
                "dialect_corrections": sum(1 for item in reviews if item["review_status"] == "DIALECT_CORRECTION"),
                "content_corrections": sum(1 for item in reviews if item["review_status"] == "CONTENT_CORRECTION"),
                "manual_additions": len(manual),
                "multi_turn_conversations": sum(1 for item in reviews + manual if len(item.get("messages", [])) > 2),
                "direct_language_texts": len(direct),
                "preference_pairs": len(preference),
                "total": len(reviews) + len(manual) + len(direct) + len(preference),
            },
        }
    finally:
        conn.close()


def _normalized(value: Any) -> str:
    text = value if isinstance(value, str) else json_dumps(value)
    return " ".join(text.casefold().split())


def _training_target(item: dict[str, Any]) -> str:
    messages = item.get("messages")
    if isinstance(messages, list) and messages:
        target_index = item.get("target_message_index")
        if not isinstance(target_index, int):
            target_index = len(messages) - 1
        if 0 <= target_index < len(messages):
            target = messages[target_index]
            if isinstance(target, dict) and target.get("role") == "assistant":
                return str(target.get("content") or "")
    if "text" in item:
        return str(item.get("text") or "")
    if "preferred_response" in item:
        return str(item.get("preferred_response") or "")
    return ""


def _near_duplicate_text(item: dict[str, Any]) -> str:
    if isinstance(item.get("messages"), list):
        return _normalized(item["messages"])
    if "text" in item:
        return _normalized(item.get("text"))
    if "preferred_response" in item:
        return _normalized([item.get("prompt_context"), item.get("preferred_response")])
    return _normalized(_training_target(item))


def _annotate_sft_record(item: dict[str, Any]) -> dict[str, Any]:
    record = dict(item)
    raw_messages = record.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise ValidationError(f"SFT record has no valid messages: {record.get('id')}")
    messages = [dict(message) if isinstance(message, dict) else message for message in raw_messages]
    record["messages"] = messages
    target_index = len(messages) - 1
    target = messages[target_index]
    if not isinstance(target, dict) or target.get("role") != "assistant" or not str(target.get("content") or "").strip():
        raise ValidationError(f"SFT record must end with a Gold assistant response: {record.get('id')}")
    record["target_message_index"] = target_index
    record["train_on_last_assistant_only"] = True
    record["message_loss_mask"] = [0] * target_index + [1]
    return record


def _duplicate_analysis(
    file_items: dict[str, list[dict[str, Any]]], remove_exact: bool = False
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    sequence = 0
    for filename, items in file_items.items():
        for index, item in enumerate(items):
            target = _normalized(_training_target(item))
            candidates.append(
                {
                    "filename": filename,
                    "index": index,
                    "sequence": sequence,
                    "id": str(item.get("id") or f"{filename}:{index}"),
                    "item": item,
                    "target": target,
                    "near_text": _near_duplicate_text(item),
                }
            )
            sequence += 1

    by_hash: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        digest = hashlib.sha256(candidate["target"].encode("utf-8")).hexdigest()
        by_hash.setdefault(digest, []).append(candidate)
    duplicate_groups = [group for group in by_hash.values() if len(group) > 1]
    removed_keys: set[tuple[str, int]] = set()
    removed_ids: list[str] = []
    kept_by_group: list[dict[str, Any]] = []
    for group in duplicate_groups:
        winner = max(
            group,
            key=lambda candidate: (
                REVIEW_DEDUP_PRIORITY.get(candidate["item"].get("review_status"), 0),
                -candidate["sequence"],
            ),
        )
        kept_by_group.append(
            {
                "kept": winner["id"],
                "removed": [candidate["id"] for candidate in group if candidate is not winner],
            }
        )
        if remove_exact:
            for candidate in group:
                if candidate is winner:
                    continue
                removed_keys.add((candidate["filename"], candidate["index"]))
                removed_ids.append(candidate["id"])

    cleaned = {
        filename: [
            item for index, item in enumerate(items) if (filename, index) not in removed_keys
        ]
        for filename, items in file_items.items()
    }
    remaining = [
        candidate
        for candidate in candidates
        if (candidate["filename"], candidate["index"]) not in removed_keys
    ]
    near = []
    for index, left in enumerate(remaining):
        for right in remaining[index + 1 :]:
            left_text = left["near_text"]
            right_text = right["near_text"]
            if (
                not left_text
                or not right_text
                or abs(len(left_text) - len(right_text)) > max(len(left_text), len(right_text)) * 0.35
            ):
                continue
            ratio = SequenceMatcher(None, left_text, right_text).ratio()
            if 0.9 <= ratio < 1:
                near.append({"left": left["id"], "right": right["id"], "similarity": round(ratio, 3)})
    report = {
        "record_count": len(candidates),
        "training_record_count_before_dedup": len(candidates),
        "training_record_count_after_dedup": len(remaining),
        "exact_duplicate_groups": [[candidate["id"] for candidate in group] for group in duplicate_groups],
        "exact_duplicate_resolution": kept_by_group,
        "exact_duplicates_removed": len(removed_ids),
        "removed_exact_duplicate_ids": removed_ids,
        "near_duplicates": near,
        "near_duplicate_count": len(near),
        "exact_comparison_basis": "normalized_gold_training_target",
        "near_comparison_basis": "normalized_record_context_and_target",
        "priority": ["APPROVED", "FULL_CORRECTION", "DIALECT_CORRECTION", "CONTENT_CORRECTION", "stable_input_order"],
    }
    return cleaned, report


def dedup_report(db_path: Path | str = DB_PATH, include_demo: bool = False) -> dict[str, Any]:
    dataset = training_dataset(db_path, include_demo)
    all_sft = [_annotate_sft_record(item) for item in dataset["reviews"] + dataset["manual_sft"]]
    _, report = _duplicate_analysis(
        {
            "sft": all_sft,
            "direct_language": dataset["direct_language"],
            "preference_pairs": dataset["preference_pairs"],
        }
    )
    return report


def _conversation_id(item: dict[str, Any]) -> str | None:
    value = item.get("conversation_id")
    return str(value) if value is not None and str(value).strip() else None


def _holdout_bounds(total_records: int) -> tuple[int, int, int]:
    goal = max(1, round(total_records * EXPORT_EVALUATION_FRACTION))
    lower = max(1, math.floor(total_records * 0.10))
    upper = max(lower, math.ceil(total_records * 0.15))
    if total_records >= 50:
        lower = max(10, lower)
        upper = max(lower, min(15, upper))
        goal = min(upper, max(lower, goal))
    return lower, goal, upper


def _stable_record_hash(scope: str, item: dict[str, Any]) -> str:
    identity = str(item.get("id") or json_dumps(item))
    return hashlib.sha256(f"{EXPORT_SPLIT_SEED}:{scope}:{identity}".encode("utf-8")).hexdigest()


def _diversity_markers(item: dict[str, Any]) -> set[str]:
    markers = set()
    if item.get("domain"):
        markers.add(f"domain:{item['domain']}")
    if item.get("review_status"):
        markers.add(f"review_status:{item['review_status']}")
    return markers


def _sample_holdout_group(
    conversation_id: str,
    entries: list[tuple[str, dict[str, Any], bool]],
    cap: int = EXPORT_EVALUATION_PER_CONVERSATION_CAP,
) -> list[tuple[str, dict[str, Any], bool]]:
    required = [entry for entry in entries if entry[2]]
    selected = list(required)
    selected_keys = {str(entry[1].get("id")) for entry in selected}
    seen = set().union(*(_diversity_markers(entry[1]) for entry in selected)) if selected else set()
    effective_cap = max(cap, len(required))
    remaining = [entry for entry in entries if str(entry[1].get("id")) not in selected_keys]
    while remaining and len(selected) < effective_cap:
        candidate = min(
            remaining,
            key=lambda entry: (
                -len(_diversity_markers(entry[1]) - seen),
                _stable_record_hash(f"holdout:{conversation_id}", entry[1]),
            ),
        )
        selected.append(candidate)
        seen.update(_diversity_markers(candidate[1]))
        remaining.remove(candidate)
    return selected


def _as_holdout(item: dict[str, Any], reason: str) -> dict[str, Any]:
    return {**item, "dataset_split": "evaluation", "holdout_reason": reason}


def _split_export_entries(
    training_entries: list[tuple[str, dict[str, Any]]],
    explicit_evaluation_entries: list[tuple[str, dict[str, Any]]],
) -> tuple[list[tuple[str, dict[str, Any]]], list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[str, list[tuple[str, dict[str, Any], bool]]] = {}
    for kind, item in training_entries:
        if conversation_id := _conversation_id(item):
            grouped.setdefault(conversation_id, []).append((kind, item, False))
    for kind, item in explicit_evaluation_entries:
        if conversation_id := _conversation_id(item):
            grouped.setdefault(conversation_id, []).append((kind, item, True))

    forced_conversations = {
        conversation_id
        for _, item in explicit_evaluation_entries
        if (conversation_id := _conversation_id(item)) is not None
    }
    selected_conversations = set(forced_conversations)
    evaluation: list[dict[str, Any]] = [
        _as_holdout(item, "evaluation_only")
        for _, item in explicit_evaluation_entries
        if _conversation_id(item) is None
    ]
    seen_markers = set().union(*(_diversity_markers(item) for item in evaluation)) if evaluation else set()
    omitted = 0
    for conversation_id in sorted(
        forced_conversations,
        key=lambda value: hashlib.sha256(f"{EXPORT_SPLIT_SEED}:{value}".encode("utf-8")).hexdigest(),
    ):
        selected = _sample_holdout_group(conversation_id, grouped[conversation_id])
        omitted += len(grouped[conversation_id]) - len(selected)
        for _, item, explicit in selected:
            reason = "evaluation_only" if explicit else "conversation_isolation"
            evaluation.append(_as_holdout(item, reason))
            seen_markers.update(_diversity_markers(item))

    total_records = len(training_entries) + len(explicit_evaluation_entries)
    available_conversations = set(grouped)
    minimum_conversations = min(3, len(available_conversations))
    lower, goal, upper = _holdout_bounds(total_records)
    candidates = set(grouped) - selected_conversations
    if total_records >= EXPORT_MIN_AUTO_SPLIT_RECORDS:
        while candidates and (
            len(evaluation) < goal or len(selected_conversations) < minimum_conversations
        ):
            options = []
            for conversation_id in candidates:
                sample = _sample_holdout_group(conversation_id, grouped[conversation_id])
                final_count = len(evaluation) + len(sample)
                outside = lower - final_count if final_count < lower else final_count - upper if final_count > upper else 0
                diversity_gain = len(
                    set().union(*(_diversity_markers(entry[1]) for entry in sample)) - seen_markers
                )
                multi_turn_cost = sum(
                    len(entry[1].get("messages", [])) > 2 for entry in grouped[conversation_id]
                )
                options.append(
                    (
                        multi_turn_cost,
                        outside,
                        abs(final_count - goal),
                        -diversity_gain,
                        len(grouped[conversation_id]) - len(sample),
                        hashlib.sha256(f"{EXPORT_SPLIT_SEED}:{conversation_id}".encode("utf-8")).hexdigest(),
                        conversation_id,
                        sample,
                    )
                )
            _, _, _, _, _, _, chosen, sample = min(options)
            selected_conversations.add(chosen)
            candidates.remove(chosen)
            omitted += len(grouped[chosen]) - len(sample)
            for _, item, _ in sample:
                evaluation.append(_as_holdout(item, "deterministic_conversation_split"))
                seen_markers.update(_diversity_markers(item))

    training = [
        (kind, item)
        for kind, item in training_entries
        if _conversation_id(item) not in selected_conversations
    ]
    split_stats = {
        "eligible_record_count": total_records,
        "evaluation_target_lower": lower,
        "evaluation_target_goal": goal,
        "evaluation_target_upper": upper,
        "evaluation_conversation_cap": EXPORT_EVALUATION_PER_CONVERSATION_CAP,
        "evaluation_records_omitted_for_conversation_isolation": omitted,
        "available_conversation_count": len(available_conversations),
        "selected_evaluation_conversation_ids": sorted(selected_conversations),
    }
    return training, evaluation, split_stats


def _balance_multi_turn_records(
    records: list[dict[str, Any]], cap: int = EXPORT_MULTI_TURN_PER_CONVERSATION_CAP
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in records:
        if conversation_id := _conversation_id(item):
            grouped.setdefault(conversation_id, []).append(item)
    selected_ids: set[str] = set()
    before_counts = {conversation_id: len(items) for conversation_id, items in grouped.items()}
    for conversation_id, items in grouped.items():
        if len(items) <= cap:
            selected_ids.update(str(item.get("id")) for item in items)
            continue
        sampled = _sample_holdout_group(
            f"multi-turn:{conversation_id}",
            [("sft", item, False) for item in items],
            cap=cap,
        )
        selected_ids.update(str(item.get("id")) for _, item, _ in sampled)
    balanced = [
        item
        for item in records
        if _conversation_id(item) is None or str(item.get("id")) in selected_ids
    ]
    after_counts = Counter(
        conversation_id
        for item in balanced
        if (conversation_id := _conversation_id(item)) is not None
    )
    return balanced, {
        "multi_turn_cap_per_conversation": cap,
        "multi_turn_records_before_balancing": len(records),
        "multi_turn_records_after_balancing": len(balanced),
        "multi_turn_records_omitted_by_balancing": len(records) - len(balanced),
        "max_multi_turn_records_per_conversation_before": max(before_counts.values(), default=0),
        "max_multi_turn_records_per_conversation_after": max(after_counts.values(), default=0),
    }


def _validate_sft_record(item: dict[str, Any], filename: str) -> None:
    if (item.get('context_complete') is False or
        (item.get('context_scope') == 'continuous_consented_segment_only' or
         str(item.get('conversation_id') or '').startswith('najdilab-chat:')) and
        item.get('context_complete') is not True):
        raise ValidationError(f"{filename}: incomplete collected context: {item.get('id')}")
    messages = item.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValidationError(f"{filename}: record has no messages: {item.get('id')}")
    if not any(isinstance(message, dict) and message.get("role") == "user" for message in messages):
        raise ValidationError(f"{filename}: record has no user message: {item.get('id')}")
    for index, message in enumerate(messages):
        if (
            not isinstance(message, dict)
            or message.get("role") not in {"system", "user", "assistant"}
            or not str(message.get("content") or "").strip()
        ):
            raise ValidationError(f"{filename}: invalid message in {item.get('id')} at {index}")
    target_index = item.get("target_message_index")
    mask = item.get("message_loss_mask")
    if (
        target_index != len(messages) - 1
        or messages[-1].get("role") != "assistant"
        or item.get("train_on_last_assistant_only") is not True
        or not isinstance(mask, list)
        or len(mask) != len(messages)
        or sum(value == 1 for value in mask) != 1
        or mask[target_index] != 1
        or any(value not in {0, 1} for value in mask)
    ):
        raise ValidationError(f"{filename}: the training target is not uniquely identified: {item.get('id')}")


def _validate_export_records(
    training_files: dict[str, list[dict[str, Any]]],
    evaluation: list[dict[str, Any]],
    include_demo: bool,
    split_stats: dict[str, Any],
    balance_stats: dict[str, Any],
) -> dict[str, Any]:
    training = [item for items in training_files.values() for item in items]
    all_gold = training + evaluation
    demo_records = sum(1 for item in all_gold if bool(item.get("demo")))
    if not include_demo and demo_records:
        raise ValidationError("Export failed: demo data was found although include_demo=false")

    target_owners: dict[str, str] = {}
    for item in training:
        target = _normalized(_training_target(item))
        if not target:
            raise ValidationError(f"Export failed: empty training target in {item.get('id')}")
        digest = hashlib.sha256(target.encode("utf-8")).hexdigest()
        if digest in target_owners:
            raise ValidationError(
                f"Export failed: exact duplicate between {target_owners[digest]} and {item.get('id')}"
            )
        target_owners[digest] = str(item.get("id"))

    training_conversations = {
        conversation_id
        for item in training
        if (conversation_id := _conversation_id(item)) is not None
    }
    evaluation_conversations = {
        conversation_id
        for item in evaluation
        if (conversation_id := _conversation_id(item)) is not None
    }
    conversation_overlap = sorted(training_conversations & evaluation_conversations)
    if conversation_overlap:
        raise ValidationError(
            "Export failed: conversation_id leakage between training and evaluation: "
            + ", ".join(conversation_overlap)
        )
    if (
        split_stats["available_conversation_count"] >= 3
        and len(evaluation_conversations) < 3
    ):
        raise ValidationError("Export failed: evaluation must span at least three conversations")
    if split_stats["eligible_record_count"] >= EXPORT_MIN_AUTO_SPLIT_RECORDS and not (
        split_stats["evaluation_target_lower"]
        <= len(evaluation)
        <= split_stats["evaluation_target_upper"]
    ):
        raise ValidationError("Export failed: evaluation size is outside the target range of 10% to 15%")
    training_ids = {str(item.get("id")) for item in training if item.get("id") is not None}
    evaluation_ids = {str(item.get("id")) for item in evaluation if item.get("id") is not None}
    id_overlap = sorted(training_ids & evaluation_ids)
    if id_overlap:
        raise ValidationError("Export failed: record ID leakage between training and evaluation: " + ", ".join(id_overlap))

    for filename in ("sft.jsonl", "multi_turn.jsonl"):
        for item in training_files.get(filename, []):
            _validate_sft_record(item, filename)
            if filename == "multi_turn.jsonl" and len(item["messages"]) <= 2:
                raise ValidationError(f"multi_turn.jsonl: record has no multi-turn context: {item.get('id')}")
            if "rejected_response" in item or "preferred_response" in item:
                raise ValidationError(f"Export failed: a preference record entered an SFT file: {item.get('id')}")
    multi_counts = Counter(
        conversation_id
        for item in training_files.get("multi_turn.jsonl", [])
        if (conversation_id := _conversation_id(item)) is not None
    )
    if max(multi_counts.values(), default=0) > balance_stats["multi_turn_cap_per_conversation"]:
        raise ValidationError("Export failed: multi-turn records exceed the per-conversation limit")
    for item in evaluation:
        if "messages" in item:
            _validate_sft_record(item, "evaluation_holdout.jsonl")

    return {
        "no_demo_when_disabled": include_demo or demo_records == 0,
        "no_exact_training_target_duplicates": True,
        "no_train_eval_conversation_overlap": True,
        "no_train_eval_id_overlap": True,
        "evaluation_has_minimum_conversation_diversity": (
            split_stats["available_conversation_count"] < 3 or len(evaluation_conversations) >= 3
        ),
        "evaluation_size_within_target_range": (
            split_stats["eligible_record_count"] < EXPORT_MIN_AUTO_SPLIT_RECORDS
            or split_stats["evaluation_target_lower"] <= len(evaluation) <= split_stats["evaluation_target_upper"]
        ),
        "multi_turn_conversation_cap_respected": True,
        "sft_targets_explicit": True,
        "jsonl_parse_valid": False,
        "training_conversation_ids": sorted(training_conversations),
        "evaluation_conversation_ids": sorted(evaluation_conversations),
        "demo_records_included": demo_records,
        "evaluation_fraction_of_eligible": round(
            len(evaluation) / split_stats["eligible_record_count"], 4
        ) if split_stats["eligible_record_count"] else 0,
    }


def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")


def _validate_jsonl_files(temp_dir: Path, files: dict[str, list[dict[str, Any]]]) -> None:
    for filename, expected_items in files.items():
        parsed = []
        with (temp_dir / filename).open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValidationError(f"{filename}:{line_number} is not valid JSON") from exc
                if not isinstance(value, dict):
                    raise ValidationError(f"{filename}:{line_number} must be an object")
                parsed.append(value)
        if len(parsed) != len(expected_items):
            raise ValidationError(f"{filename}: written record count does not match the expected count")


def create_export(
    db_path: Path | str = DB_PATH,
    exports_dir: Path | str | None = None,
    include_demo: bool = False,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    readiness = export_readiness(db_path, include_demo=include_demo)
    if not readiness["ok"]:
        raise ExportReadinessError(readiness)
    exports_dir = Path(exports_dir or ROOT / "exports")
    exports_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        with transaction(conn):
            privacy = export_privacy(conn,include_demo=include_demo)
            if not privacy['ok']:
                raise ExportReadinessError(privacy)
            number = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM dataset_versions").fetchone()[0]
            version = f"gold-v{number:03d}"
            if (exports_dir / version).exists():
                raise ValidationError("The version directory already exists")
            dataset = training_dataset(db_path, include_demo)
            reviews = dataset["reviews"]
            manual = dataset["manual_sft"]
            training_entries = (
                [("sft", _annotate_sft_record(item)) for item in reviews + manual]
                + [("direct_language", item) for item in dataset["direct_language"]]
                + [("preference_pairs", item) for item in dataset["preference_pairs"]]
            )
            explicit_evaluation_entries = (
                [
                    ("sft", _annotate_sft_record(item))
                    for item in (
                        _review_training_records(conn, include_demo, evaluation=True)
                        + _manual_records(conn, "manual_sft_items", include_demo, evaluation=True)
                    )
                ]
                + [
                    ("direct_language", item)
                    for item in _manual_records(conn, "direct_language_texts", include_demo, evaluation=True)
                ]
                + [
                    ("preference_pairs", item)
                    for item in _manual_records(conn, "preference_pairs", include_demo, evaluation=True)
                ]
            )
            archive = {
                "conversations": [dict(x) for x in conn.execute("SELECT * FROM conversations")],
                "messages": [dict(x) for x in conn.execute("SELECT * FROM messages")],
                "reviews": [dict(x) for x in conn.execute("SELECT * FROM reviews")],
                "review_tags": [dict(x) for x in conn.execute("SELECT * FROM review_tags")],
                "manual_sft_items": [dict(x) for x in conn.execute("SELECT * FROM manual_sft_items")],
                "direct_language_texts": [dict(x) for x in conn.execute("SELECT * FROM direct_language_texts")],
                "preference_pairs": [dict(x) for x in conn.execute("SELECT * FROM preference_pairs")],
            }
        training_entries, evaluation, split_stats = _split_export_entries(
            training_entries, explicit_evaluation_entries
        )
        training_sft = [item for kind, item in training_entries if kind == "sft"]
        multi_turn_before_balancing = [
            item for item in training_sft if len(item.get("messages", [])) > 2
        ]
        balanced_multi_turn, balance_stats = _balance_multi_turn_records(
            multi_turn_before_balancing
        )
        raw_training_files = {
            "sft.jsonl": [item for item in training_sft if len(item.get("messages", [])) <= 2],
            "multi_turn.jsonl": balanced_multi_turn,
            "direct_language.jsonl": [
                item for kind, item in training_entries if kind == "direct_language"
            ],
            "preference_pairs.jsonl": [
                item for kind, item in training_entries if kind == "preference_pairs"
            ],
        }
        training_files, dedup = _duplicate_analysis(raw_training_files, remove_exact=True)
        final_multi_counts = Counter(
            conversation_id
            for item in training_files["multi_turn.jsonl"]
            if (conversation_id := _conversation_id(item)) is not None
        )
        balance_stats["multi_turn_records_after_export"] = len(training_files["multi_turn.jsonl"])
        balance_stats["max_multi_turn_records_per_conversation_after_export"] = max(
            final_multi_counts.values(), default=0
        )
        validation = _validate_export_records(
            training_files, evaluation, include_demo, split_stats, balance_stats
        )
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=exports_dir))
        final_dir = exports_dir / version
        try:
            files = {**training_files, "evaluation_holdout.jsonl": evaluation}
            for name, items in files.items():
                _write_jsonl(temp_dir / name, items)
            _validate_jsonl_files(temp_dir, files)
            validation["jsonl_parse_valid"] = True
            (temp_dir / "full_archive.json").write_text(
                json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (temp_dir / "dedup_report.json").write_text(
                json.dumps(dedup, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            sha256 = {}
            for path in sorted(temp_dir.iterdir()):
                sha256[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            status_counts = Counter(item.get("review_status") for item in reviews)
            source_models = sorted({item.get("model_name") for item in reviews if item.get("model_name")})
            language_layers = sorted(
                {item.get("language_layer") for item in manual + dataset["direct_language"] + dataset["preference_pairs"] if item.get("language_layer")}
            )
            domains = sorted(
                {item.get("domain") for item in manual + dataset["direct_language"] + dataset["preference_pairs"] if item.get("domain")}
            )
            excluded_count = conn.execute(
                "SELECT (SELECT COUNT(*) FROM reviews WHERE exclude_from_training = 1) + "
                "(SELECT COUNT(*) FROM manual_sft_items WHERE exclude_from_training = 1) + "
                "(SELECT COUNT(*) FROM direct_language_texts WHERE exclude_from_training = 1) + "
                "(SELECT COUNT(*) FROM preference_pairs WHERE exclude_from_training = 1)"
            ).fetchone()[0]
            lifecycle_counts = conn.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM reviews WHERE review_status = 'IGNORED')
                    + (SELECT COUNT(*) FROM manual_sft_items WHERE ignored_at IS NOT NULL AND deleted_at IS NULL)
                    + (SELECT COUNT(*) FROM direct_language_texts WHERE ignored_at IS NOT NULL AND deleted_at IS NULL)
                    + (SELECT COUNT(*) FROM preference_pairs WHERE ignored_at IS NOT NULL AND deleted_at IS NULL) AS ignored_count,
                  (SELECT COUNT(*) FROM reviews WHERE review_status = 'DELETED')
                    + (SELECT COUNT(*) FROM manual_sft_items WHERE deleted_at IS NOT NULL)
                    + (SELECT COUNT(*) FROM direct_language_texts WHERE deleted_at IS NOT NULL)
                    + (SELECT COUNT(*) FROM preference_pairs WHERE deleted_at IS NOT NULL) AS deleted_count
                """
            ).fetchone()
            manifest = {
                "version": version,
                "state": "Frozen",
                "privacy_policy": "no_flagged_or_excluded_context_v1",
                "created_at": utc_now(),
                "record_count": sum(len(items) for items in files.values()),
                "training_record_count": sum(len(items) for items in training_files.values()),
                "evaluation_record_count": len(evaluation),
                "training_conversation_count": len(validation["training_conversation_ids"]),
                "evaluation_conversation_count": len(validation["evaluation_conversation_ids"]),
                "exact_duplicates_removed": dedup["exact_duplicates_removed"],
                "near_duplicate_count": dedup["near_duplicate_count"],
                "demo_records_included": validation["demo_records_included"],
                "split_seed": EXPORT_SPLIT_SEED,
                "include_demo": include_demo,
                "evaluation_split": split_stats,
                "multi_turn_balancing": balance_stats,
                "multi_turn_cap_per_conversation": balance_stats["multi_turn_cap_per_conversation"],
                "max_multi_turn_records_per_conversation": balance_stats[
                    "max_multi_turn_records_per_conversation_after_export"
                ],
                "files": {name: len(items) for name, items in files.items()},
                "source_models": source_models,
                "review_status_counts": dict(status_counts),
                "language_layers": language_layers,
                "domains": domains,
                "sha256": sha256,
                "excluded_count": excluded_count,
                "evaluation_only_count": len(evaluation),
                "ignored_count": lifecycle_counts["ignored_count"],
                "deleted_count": lifecycle_counts["deleted_count"],
                "filters_used": {**(filters or {}), "include_demo": include_demo},
                "validation": validation,
            }
            # Diagnostics belong to the version from its first moment: generate them in the staging folder,
            # bound to this version name and the training files' fingerprint, before it is published as
            # Frozen (V2.2.0; earlier versions needed a derived Draft just to obtain them).
            from .dataset_platform import _generate_training_diagnostics
            _generate_training_diagnostics(temp_dir, manifest)
            (temp_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(temp_dir, final_dir)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        with transaction(conn):
            dataset_cursor = conn.execute(
                "INSERT INTO dataset_versions(version, created_at, record_count, manifest_json, export_path, filters_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    version,
                    manifest["created_at"],
                    manifest["record_count"],
                    json_dumps(manifest),
                    str(final_dir),
                    json_dumps(manifest["filters_used"]),
                ),
            )
            for exported_items in files.values():
                for item in exported_items:
                    exported_id = str(item.get("id") or "")
                    if ":" not in exported_id:
                        continue
                    table, raw_id = exported_id.split(":", 1)
                    item_type = MANUAL_TYPES_BY_TABLE.get(table)
                    if item_type and raw_id.isdigit():
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO manual_data_export_history(
                                item_type, item_id, dataset_version_id, exported_at
                            ) VALUES (?, ?, ?, ?)
                            """,
                            (item_type, int(raw_id), dataset_cursor.lastrowid, manifest["created_at"]),
                        )
        return {"version": version, "path": str(final_dir), "manifest": manifest, "dedup_report": dedup}
    finally:
        conn.close()


def list_exports(db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    conn = connect(db_path)
    try:
        return [dict(row) for row in conn.execute("SELECT * FROM dataset_versions ORDER BY id DESC")]
    finally:
        conn.close()


def analytics(db_path: Path | str = DB_PATH) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        summary = dict(
            conn.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM conversations) AS total_conversations,
                  (SELECT COUNT(*) FROM messages WHERE role = 'assistant') AS total_responses,
                  SUM(CASE WHEN review_status = 'PENDING' THEN 1 ELSE 0 END) AS pending_reviews,
                  SUM(CASE WHEN review_status = 'APPROVED' THEN 1 ELSE 0 END) AS approved,
                  SUM(CASE WHEN review_status = 'DIALECT_CORRECTION' THEN 1 ELSE 0 END) AS dialect_corrections,
                  SUM(CASE WHEN review_status = 'CONTENT_CORRECTION' THEN 1 ELSE 0 END) AS content_corrections,
                  SUM(CASE WHEN review_status = 'FULL_CORRECTION' THEN 1 ELSE 0 END) AS full_corrections,
                  SUM(CASE WHEN review_status = 'IGNORED' THEN 1 ELSE 0 END) AS ignored,
                  SUM(CASE WHEN review_status = 'DELETED' THEN 1 ELSE 0 END) AS deleted,
                  SUM(CASE WHEN review_status IN ('APPROVED','FULL_CORRECTION','DIALECT_CORRECTION','CONTENT_CORRECTION') AND training_eligible = 1 THEN 1 ELSE 0 END) AS training_eligible_count,
                  SUM(CASE WHEN review_status IN ('APPROVED','FULL_CORRECTION','DIALECT_CORRECTION','CONTENT_CORRECTION') THEN 1 ELSE 0 END) AS reviewed_count
                FROM reviews
                """
            ).fetchone()
        )
        reviewed = summary.get("reviewed_count") or 0
        for key in ("approved", "dialect_corrections", "content_corrections", "full_corrections"):
            summary[f"{key}_pct"] = round((summary.get(key) or 0) * 100 / reviewed, 1) if reviewed else 0
        by_model = [
            dict(row)
            for row in conn.execute(
                """
                SELECT COALESCE(c.model_name, 'Unspecified') AS name, COUNT(r.id) AS total,
                  ROUND(100.0 * SUM(r.review_status = 'APPROVED') / NULLIF(SUM(r.review_status IN ('APPROVED','FULL_CORRECTION','DIALECT_CORRECTION','CONTENT_CORRECTION')), 0), 1) AS approval_rate,
                  ROUND(100.0 * SUM(r.review_status = 'DIALECT_CORRECTION') / NULLIF(SUM(r.review_status IN ('APPROVED','FULL_CORRECTION','DIALECT_CORRECTION','CONTENT_CORRECTION')), 0), 1) AS dialect_error_rate,
                  ROUND(100.0 * SUM(r.review_status IN ('CONTENT_CORRECTION','FULL_CORRECTION')) / NULLIF(SUM(r.review_status IN ('APPROVED','FULL_CORRECTION','DIALECT_CORRECTION','CONTENT_CORRECTION')), 0), 1) AS content_error_rate
                FROM reviews r JOIN messages m ON m.id = r.message_id
                JOIN conversations c ON c.id = m.conversation_id GROUP BY c.model_name ORDER BY total DESC
                """
            )
        ]
        by_channel = [
            dict(row)
            for row in conn.execute("SELECT channel AS name, COUNT(*) AS count FROM conversations GROUP BY channel ORDER BY count DESC")
        ]
        top_tags = [
            dict(row)
            for row in conn.execute("SELECT tag AS name, COUNT(*) AS count FROM review_tags GROUP BY tag ORDER BY count DESC LIMIT 10")
        ]
        return {"summary": summary, "by_model": by_model, "by_channel": by_channel, "top_tags": top_tags}
    finally:
        conn.close()


def seed_demo_data(db_path: Path | str = DB_PATH) -> int:
    conn = connect(db_path)
    try:
        if conn.execute("SELECT COUNT(*) FROM conversations WHERE demo = 1").fetchone()[0]:
            return 0
    finally:
        conn.close()
    samples = [
        ("Najdi greeting", "web", "ollama", "najdi-demo:latest", "وش أفضل وقت أزور فيه الرياض؟", "يمكنك زيارة الرياض في أي وقت. درجات الحرارة جيدة.", None),
        ("Dinner suggestions", "whatsapp", "ollama", "najdi-demo:latest", "أبي مطعم شعبي قريب", "أنصحك بمطعم إيطالي فاخر.", None),
        ("Technical information", "cli", "local", "coder-demo", "اشرح لي WAL في SQLite باختصار", "WAL يسجل التغييرات في ملف منفصل ويساعد على تزامن القراءة والكتابة.", "APPROVED"),
        ("Najdi phrasing", "telegram", "cloud", "arabic-demo", "قلها بلهجة الرياض: لا تقلق", "لا تشعر بالقلق.", "DIALECT_CORRECTION"),
        ("Multi-turn context", "web", "local", "context-demo", "تذكر أن ميزانيتي ١٠٠ ريال", "حاضر، ميزانيتك ١٠٠ ريال.", None),
        ("Local facts", "api", "cloud", "facts-demo", "وش عاصمة السعودية؟", "عاصمة السعودية جدة.", "CONTENT_CORRECTION"),
        ("Verbose response", "manual", "local", "najdi-demo:latest", "اختصر لي فكرة المشروع", "هذا المشروع عبارة عن منظومة طويلة جدًا تهدف إلى جمع البيانات ثم مراجعتها والاستفادة منها مستقبلًا في عدة سياقات متعددة.", "FULL_CORRECTION"),
    ]
    count = 0
    for index, (title, channel, provider, model, user, assistant, status) in enumerate(samples, 1):
        result = ingest_turn(
            {
                "conversation_id": f"demo-{index:03d}",
                "title": title,
                "source": "manual",
                "channel": channel,
                "provider": provider,
                "model_name": model,
                "user_message": user,
                "assistant_response": assistant,
                "demo": True,
                "metadata": {"purpose": "NajdiLab demo"},
            },
            db_path,
        )
        if status:
            corrected = {
                "DIALECT_CORRECTION": "لا تشيل هم.",
                "CONTENT_CORRECTION": "عاصمة السعودية هي الرياض.",
                "FULL_CORRECTION": "منصة تجمع المحادثات وتراجعها وتحول المعتمد منها إلى بيانات ذهبية.",
            }.get(status)
            save_review(
                result["review_id"],
                {
                    "review_status": status,
                    "corrected_response": corrected,
                    "training_eligible": True,
                    "tags": [] if status == "APPROVED" else ["dialect_issue" if status == "DIALECT_CORRECTION" else "factual_error" if status == "CONTENT_CORRECTION" else "too_verbose"],
                    "review_notes": "Demo review",
                },
                db_path,
            )
        if index == 5:
            ingest_turn(
                {
                    "conversation_id": "demo-005",
                    "title": title,
                    "source": "manual",
                    "channel": channel,
                    "provider": provider,
                    "model_name": model,
                    "user_message": "طيب اقترح نشاطًا يناسبها",
                    "assistant_response": "احجز تجربة خاصة سعرها ٣٥٠ ريال.",
                    "demo": True,
                    "metadata": {"purpose": "NajdiLab multi-turn demo"},
                },
                db_path,
            )
        count += 1
    add_manual_sft(
        {
            "messages": [
                {"role": "user", "content": "وش يسوي NajdiLab؟"},
                {"role": "assistant", "content": "يجمع المحادثات ويرتب مراجعتها ويحفظ البيانات المعتمدة."},
            ],
            "language_layer": "najdi_riyadh",
            "domain": "product",
            "origin": "manual",
            "training_eligible": True,
            "demo": True,
        },
        db_path,
    )
    add_direct_text(
        {
            "text": "يا هلا ومرحبا، أبشر بسعدك.",
            "language_layer": "najdi_riyadh",
            "domain": "greetings",
            "source": "demo",
            "source_type": "human_written",
            "origin": "manual",
            "training_eligible": True,
            "demo": True,
        },
        db_path,
    )
    add_preference_pair(
        {
            "prompt_context": "اختصر الرد باللهجة السعودية.",
            "rejected_response": "سوف أقوم بذلك بكل تأكيد.",
            "preferred_response": "أبشر.",
            "language_layer": "saudi_neutral",
            "domain": "style",
            "origin": "synthetic_reviewed",
            "training_eligible": True,
            "demo": True,
        },
        db_path,
    )
    return count
