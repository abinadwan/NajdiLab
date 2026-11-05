from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .db import DB_PATH
from .collection_context import collection_context

CORRECTIONS = {"FULL_CORRECTION", "DIALECT_CORRECTION", "CONTENT_CORRECTION"}
DECISIONS = {"APPROVED", *CORRECTIONS}
INACTIVE_STATUSES = {"IGNORED", "DELETED"}
MANUAL_TABLES = ("manual_sft_items", "direct_language_texts", "preference_pairs")
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

    # Reviews with id <= legacy_max_review_id predate the audit trail (reviews.id is
    # AUTOINCREMENT). A missing baseline fails closed: every review then requires events.
    legacy_max_review_id = 0
    if event_table and _table_exists(conn, "review_event_baseline"):
        baseline = conn.execute("SELECT legacy_max_review_id FROM review_event_baseline WHERE id=1").fetchone()
        legacy_max_review_id = int(baseline[0]) if baseline else 0

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
        elif status in INACTIVE_STATUSES and corrected is not None:
            findings.append(_finding(
                "REVIEW_PRESERVED_CORRECTION_INACTIVE", sample_id,
                "This review was ignored or deleted; its earlier correction is kept for a possible restore and is never exported",
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
                if int(row["id"]) <= legacy_max_review_id:
                    findings.append(_finding(
                        "REVIEW_HISTORY_UNVERIFIABLE", sample_id,
                        "This review predates the event audit trail; its current decision is checked, but its transition history cannot be verified",
                        "WARNING", confirmed=False,
                        details={"legacy_max_review_id": legacy_max_review_id},
                    ))
                else:
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


def eligible_records(conn: sqlite3.Connection, *, include_demo: bool = False) -> list[str]:
    """Every record a build may include today: active, eligible (training or evaluation), not excluded."""
    ids = [f"review:{row[0]}" for row in conn.execute(
        """SELECT r.id FROM reviews r JOIN messages m ON m.id=r.message_id JOIN conversations c ON c.id=m.conversation_id
           WHERE r.review_status IN ('APPROVED','FULL_CORRECTION','DIALECT_CORRECTION','CONTENT_CORRECTION')
           AND r.exclude_from_training=0 AND (r.training_eligible=1 OR r.evaluation_only=1) AND (?=1 OR c.demo=0)
           ORDER BY r.id""", (int(include_demo),))]
    for table in MANUAL_TABLES:
        ids += [f"{table}:{row[0]}" for row in conn.execute(
            f"""SELECT id FROM {table} WHERE archived=0 AND exclude_from_training=0 AND deleted_at IS NULL
                AND ignored_at IS NULL AND (training_eligible=1 OR evaluation_only=1) AND (?=1 OR demo=0) ORDER BY id""",
            (int(include_demo),))]
    return ids


def resolve_selection(conn: sqlite3.Connection, selection, *, include_demo: bool = False) -> list[str]:
    """The records a build includes: all eligible records, or exactly the chosen ones (each must be eligible)."""
    eligible = eligible_records(conn, include_demo=include_demo)
    if selection is None:
        return eligible
    if not isinstance(selection, (list, tuple)) or not all(isinstance(x, str) for x in selection):
        raise ValueError("selection must be a list of record ids")
    unknown = sorted(set(selection) - set(eligible))
    if unknown:
        raise ValueError("Only eligible, active records can be selected: " + ", ".join(unknown[:5]))
    return [x for x in eligible if x in set(selection)]


def export_privacy(conn: sqlite3.Connection, *, include_demo: bool = False, selection: list[str] | None = None) -> dict[str, Any]:
    """Block a whole window; never trim excluded/private context silently."""
    findings = []
    chosen = None if selection is None else set(selection)
    for review_id, source, metadata in conn.execute('''SELECT r.id, c.source, c.metadata_json FROM reviews r
        JOIN messages m ON m.id=r.message_id JOIN conversations c ON c.id=m.conversation_id
        WHERE r.review_status IN ('APPROVED','FULL_CORRECTION','DIALECT_CORRECTION','CONTENT_CORRECTION')
        AND r.exclude_from_training=0 AND (r.training_eligible=1 OR r.evaluation_only=1)
        AND (?=1 OR c.demo=0)''', (int(include_demo),)):
        if chosen is not None and f'review:{review_id}' not in chosen:
            continue
        if collection_context({'source': source, 'metadata_json': metadata}).get('context_complete') is False:
            findings.append(_finding('EXPORT_INCOMPLETE_CONTEXT', f'review:{review_id}',
                'The selected collected chat has missing or unverifiable earlier context. '
                'Review remains available; training and evaluation export require a complete consented context.',
                'ERROR', confirmed=True))
    rows = conn.execute('''SELECT DISTINCT r.id FROM reviews r
        JOIN messages m ON m.id=r.message_id JOIN conversations c ON c.id=m.conversation_id
        WHERE r.review_status IN ('APPROVED','FULL_CORRECTION','DIALECT_CORRECTION','CONTENT_CORRECTION')
        AND r.exclude_from_training=0 AND (r.training_eligible=1 OR r.evaluation_only=1)
        AND (?=1 OR c.demo=0) AND EXISTS (
            SELECT 1 FROM messages p JOIN reviews pr ON pr.message_id=p.id
            WHERE p.conversation_id=m.conversation_id AND p.turn_index<=m.turn_index
            AND (pr.contains_personal_data=1 OR pr.contains_sensitive_data=1 OR pr.exclude_from_training=1
                 OR pr.review_status IN ('IGNORED','DELETED') OR (r.training_eligible=1 AND pr.evaluation_only=1))
        )''', (int(include_demo),)).fetchall()
    for row in rows:
        if chosen is not None and f'review:{row[0]}' not in chosen:
            continue
        findings.append(_finding('EXPORT_PRIVATE_CONTEXT',f'review:{row[0]}',
            'A selected target or its full context contains privacy-flagged, excluded, deleted or evaluation-only data. Resolve the review or exclude the whole target; context was not trimmed.',
            'ERROR',confirmed=True))
    for table in ('manual_sft_items','direct_language_texts','preference_pairs'):
        for row in conn.execute(f'''SELECT id FROM {table} WHERE archived=0 AND exclude_from_training=0
            AND deleted_at IS NULL AND ignored_at IS NULL AND (training_eligible=1 OR evaluation_only=1)
            AND (contains_personal_data=1 OR contains_sensitive_data=1) AND (?=1 OR demo=0)''', (int(include_demo),)):
            if chosen is not None and f'{table}:{row[0]}' not in chosen:
                continue
            findings.append(_finding('EXPORT_PRIVATE_TARGET',f'{table}:{row[0]}',
                'An eligible manual record has a privacy flag; resolve or exclude it before export.', 'ERROR',confirmed=True))
    return _result(findings,include_demo)


def export_readiness(db_path: Path | str = DB_PATH, *, include_demo: bool = False, selection: list[str] | None = None) -> dict[str, Any]:
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
            try:
                chosen = resolve_selection(conn, selection, include_demo=include_demo)
            except ValueError as exc:
                return _result([*result["findings"], _finding("SELECTION_INVALID", None, str(exc), "ERROR", confirmed=True)], include_demo)
            privacy = export_privacy(conn, include_demo=include_demo, selection=chosen)
            # Review integrity stays fail-closed for the whole database; privacy is checked for the records exported.
            result = _result([*result['findings'], *privacy['findings']], include_demo)
            exportable = len(chosen)
        except sqlite3.Error as exc:
            extra = _finding("EXPORT_SOURCE_DATA_UNAVAILABLE", None, "Unable to verify export data sources", "ERROR", confirmed=True,
                             details={"error": type(exc).__name__})
            return _result([*result["findings"], extra], include_demo)
        if exportable == 0:
            result = _result([*result["findings"], _finding(
                "NO_EXPORTABLE_DATA", None, "No reviewed records or manual data are eligible for a build", "ERROR", confirmed=True
            )], include_demo)
        result["exportable_records"] = int(exportable)
        result["selection"] = chosen
        result["policy"] = "fail_closed_confirmed_errors; ambiguous_findings_warn_only; frozen_releases_unchanged"
        return result
    finally:
        conn.close()

