from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .db import DB_PATH

CORRECTIONS = {"FULL_CORRECTION", "DIALECT_CORRECTION", "CONTENT_CORRECTION"}
DECISIONS = {"APPROVED", *CORRECTIONS}
INACTIVE = {"IGNORED", "DELETED"}


class ExportReadinessError(ValueError):
    def __init__(self, readiness: dict[str, Any]):
        self.readiness = readiness
        blockers = readiness.get("blocking_findings") or []
        summary = "; ".join(
            f"{item['code']} ({item.get('sample_id') or 'global'}): {item['reason']}" for item in blockers[:5]
        )
        if len(blockers) > 5:
            summary += f"; +{len(blockers) - 5} more"
        super().__init__(f"Data export is blocked: {summary or 'Readiness check failed'}")


def _normalized(value: str | None) -> str:
    return " ".join(str(value or "").casefold().split())


def _sha256(value: str | None) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _finding(
    code: str,
    sample_id: str | None,
    reason: str,
    severity: str,
    *,
    confirmed: bool,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "sample_id": sample_id,
        "reason": reason,
        "severity": severity,
        "confirmed": confirmed,
        "blocking": confirmed and severity == "ERROR",
        "details": details or {},
    }


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def review_integrity(conn: sqlite3.Connection, *, include_demo: bool = False) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    findings: list[dict[str, Any]] = []
    try:
        rows = conn.execute(
            """
            SELECT r.*, m.content AS message_content, m.role AS message_role,
                   m.id AS source_message_id, c.external_conversation_id, c.demo
            FROM reviews r
            LEFT JOIN messages m ON m.id = r.message_id
            LEFT JOIN conversations c ON c.id = m.conversation_id
            WHERE (? = 1 OR COALESCE(c.demo, 0) = 0)
            ORDER BY r.id
            """,
            (int(include_demo),),
        ).fetchall()
        missing = conn.execute(
            """
            SELECT m.id, c.external_conversation_id
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            LEFT JOIN reviews r ON r.message_id = m.id
            WHERE m.role='assistant' AND r.id IS NULL AND (? = 1 OR c.demo=0)
            ORDER BY m.id
            """,
            (int(include_demo),),
        ).fetchall()
    except sqlite3.Error as exc:
        finding = _finding("REVIEW_DATA_UNAVAILABLE", None, "Unable to read the review relationships required for export", "ERROR",
                           confirmed=True, details={"error": type(exc).__name__})
        return _result([finding], include_demo)

    for item in missing:
        findings.append(_finding(
            "REVIEW_MISSING", f"message:{item['id']}", "Assistant message has no review decision", "ERROR", confirmed=True,
            details={"conversation_id": item["external_conversation_id"]},
        ))

    event_table = _table_exists(conn, "review_events")
    if not event_table:
        findings.append(_finding(
            "REVIEW_HISTORY_UNAVAILABLE", None,
            "Review events have not been migrated; current state can be inspected, but the complete historical sequence cannot be established",
            "WARNING", confirmed=False,
        ))

    for row in rows:
        sample_id = f"review:{row['id']}"
        status = str(row["review_status"] or "")
        corrected = row["corrected_response"]
        if row["source_message_id"] is None:
            findings.append(_finding("REVIEW_SOURCE_MISSING", sample_id, "The review is not linked to an existing original message", "ERROR", confirmed=True))
            continue
        if row["message_role"] != "assistant":
            findings.append(_finding("REVIEW_SOURCE_ROLE_INVALID", sample_id, "The review is linked to a message whose role is not assistant", "ERROR", confirmed=True))
        if not str(row["original_response"] or "").strip():
            findings.append(_finding("REVIEW_ORIGINAL_MISSING", sample_id, "The original response snapshot is missing", "ERROR", confirmed=True))
        elif row["original_response"] != row["message_content"]:
            if _normalized(row["original_response"]) == _normalized(row["message_content"]):
                findings.append(_finding(
                    "REVIEW_SOURCE_FORMAT_DRIFT", sample_id,
                    "The original response and source message differ only in formatting; human verification is required before marking the review stale",
                    "WARNING", confirmed=False,
                ))
            else:
                findings.append(_finding(
                    "REVIEW_SOURCE_STALE", sample_id, "The source message changed after the review snapshot was created", "ERROR", confirmed=True,
                    details={"recorded_sha256": _sha256(row["original_response"]), "current_sha256": _sha256(row["message_content"])},
                ))
        if status == "PENDING":
            findings.append(_finding("REVIEW_PENDING", sample_id, "The required review decision is unresolved", "ERROR", confirmed=True))
        if status in CORRECTIONS and not str(corrected or "").strip():
            findings.append(_finding("REVIEW_CORRECTION_MISSING", sample_id, "The correction status has no corrected text", "ERROR", confirmed=True))
        if status == "PENDING" and corrected is not None:
            findings.append(_finding(
                "REVIEW_PRESERVED_CORRECTION_PENDING", sample_id,
                "A correction from a previous decision is retained but remains inactive until the restored review is resolved",
                "WARNING", confirmed=False,
            ))
        elif status not in CORRECTIONS and corrected is not None:
            findings.append(_finding("REVIEW_CORRECTION_STATUS_CONFLICT", sample_id, "Corrected text exists with a status that does not represent a correction", "ERROR", confirmed=True))
        if bool(row["training_eligible"]) and status not in DECISIONS:
            findings.append(_finding("REVIEW_ELIGIBILITY_CONFLICT", sample_id, "An unresolved or inactive sample is marked for training", "ERROR", confirmed=True))
        if bool(row["training_eligible"]) and bool(row["evaluation_only"]):
            findings.append(_finding("REVIEW_SPLIT_CONFLICT", sample_id, "The sample is marked for both training and evaluation-only use", "ERROR", confirmed=True))
        if not str(row["reviewer"] or "").strip():
            findings.append(_finding("REVIEW_PROVENANCE_MISSING", sample_id, "The review decision source identity is missing", "ERROR", confirmed=True))

        if event_table:
            events = conn.execute(
                "SELECT sequence,to_status,source_sha256 FROM review_events WHERE review_id=? ORDER BY sequence", (row["id"],)
            ).fetchall()
            if not events:
                findings.append(_finding("REVIEW_EVENT_MISSING", sample_id, "The current state has no recorded review event", "ERROR", confirmed=True))
            else:
                expected = list(range(1, len(events) + 1))
                actual = [event["sequence"] for event in events]
                if actual != expected:
                    findings.append(_finding("REVIEW_EVENT_SEQUENCE_CONFLICT", sample_id, "The review event sequence is discontinuous", "ERROR", confirmed=True,
                                             details={"expected": expected, "actual": actual}))
                latest = events[-1]
                if latest["to_status"] != status:
                    findings.append(_finding("REVIEW_EVENT_STATUS_CONFLICT", sample_id, "The latest event does not match the current status", "ERROR", confirmed=True))
                if latest["source_sha256"] != _sha256(row["message_content"]):
                    findings.append(_finding("REVIEW_EVENT_SOURCE_STALE", sample_id, "The source fingerprint in the latest event is stale", "ERROR", confirmed=True))

    return _result(findings, include_demo)


def _result(findings: list[dict[str, Any]], include_demo: bool) -> dict[str, Any]:
    blocking = [item for item in findings if item["blocking"]]
    ambiguous = [item for item in findings if not item["confirmed"]]
    return {
        "ok": not blocking,
        "status": "READY" if not blocking else "BLOCKED",
        "include_demo": include_demo,
        "findings": findings,
        "blocking_findings": blocking,
        "ambiguous_findings": ambiguous,
        "counts": {
            "total": len(findings), "blocking": len(blocking), "ambiguous": len(ambiguous),
            "errors": sum(item["severity"] == "ERROR" for item in findings),
            "warnings": sum(item["severity"] == "WARNING" for item in findings),
        },
    }


def export_readiness(db_path: Path | str = DB_PATH, *, include_demo: bool = False) -> dict[str, Any]:
    path = Path(db_path)
    try:
        conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except (sqlite3.Error, OSError) as exc:
        return _result([_finding("DATABASE_UNAVAILABLE", None, "The source database is unavailable", "ERROR", confirmed=True,
                                 details={"error": type(exc).__name__})], include_demo)
    try:
        result = review_integrity(conn, include_demo=include_demo)
        try:
            exportable = conn.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM reviews r
                     JOIN messages m ON m.id=r.message_id
                     JOIN conversations c ON c.id=m.conversation_id
                     WHERE r.review_status IN ('APPROVED','FULL_CORRECTION','DIALECT_CORRECTION','CONTENT_CORRECTION')
                     AND r.exclude_from_training=0 AND (r.training_eligible=1 OR r.evaluation_only=1)
                     AND (?=1 OR c.demo=0))
                + (SELECT COUNT(*) FROM manual_sft_items WHERE archived=0 AND exclude_from_training=0 AND deleted_at IS NULL AND ignored_at IS NULL AND (training_eligible=1 OR evaluation_only=1))
                + (SELECT COUNT(*) FROM direct_language_texts WHERE archived=0 AND exclude_from_training=0 AND deleted_at IS NULL AND ignored_at IS NULL AND (training_eligible=1 OR evaluation_only=1))
                + (SELECT COUNT(*) FROM preference_pairs WHERE archived=0 AND exclude_from_training=0 AND deleted_at IS NULL AND ignored_at IS NULL AND (training_eligible=1 OR evaluation_only=1))
                """
            , (int(include_demo),)).fetchone()[0]
        except sqlite3.Error as exc:
            extra = _finding("EXPORT_SOURCE_DATA_UNAVAILABLE", None, "Unable to verify export data sources", "ERROR", confirmed=True,
                             details={"error": type(exc).__name__})
            return _result([*result["findings"], extra], include_demo)
        if exportable == 0:
            result = _result([*result["findings"], _finding(
                "NO_EXPORTABLE_DATA", None, "No reviewed records or manual data are eligible for a build", "ERROR", confirmed=True
            )], include_demo)
        result["exportable_records"] = int(exportable)
        result["policy"] = "fail_closed_confirmed_errors; ambiguous_findings_warn_only; frozen_releases_unchanged"
        return result
    finally:
        conn.close()

