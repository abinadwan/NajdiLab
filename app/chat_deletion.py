"""Permanent deletion of one NajdiLab chat conversation (Chat V2).

Declared scope (docs/data-retention.md):
- Deleted: the session row, its model binding, every request receipt and every
  turn's text in the chat tables.
- Collected review copies of this session (``najdilab-chat:<id>:*``):
  deleted outright when no immutable review event refers to them; otherwise
  their text, titles, notes, tags and metadata are overwritten and the review
  is marked DELETED, so only the content-free events (status, actor, time,
  SHA-256 of the old text) remain as proof that a review happened.
- SQLite: the deleting connection uses ``secure_delete`` so freed pages are
  zeroed, then the WAL is checkpointed and truncated (best effort; reported).

Refused, not partially done: an active or RUNNING turn, a stale revision, or
any copy in NajdiLab's own export/dataset folders (frozen files are never
rewritten). Never touched and reported instead: backups and any copy outside
NajdiLab's control. The tombstone in ``chat_deletions`` holds counts only.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Iterable
from uuid import uuid4

from .db import utc_now
from .integrations import IntegrationError

POLICY = "chat-permanent-delete-v1"
CONFIRMATION = "DELETE"
REDACTED = "[deleted]"
SCANNED_SUFFIXES = {".json", ".jsonl", ".csv", ".tsv", ".txt", ".md", ".parquet"}
SCAN_FILE_LIMIT = 20000
CHUNK = 1024 * 1024


def _marker(sid: str) -> str:
    return f"najdilab-chat:{sid}"


def review_conversations(conn: sqlite3.Connection, sid: str) -> list[int]:
    rows = conn.execute(
        """SELECT review_conversation_id AS id FROM chat_turns WHERE session_id=? AND review_conversation_id IS NOT NULL
           UNION SELECT id FROM conversations WHERE external_conversation_id LIKE ? ESCAPE '\\'""",
        (sid, _marker(sid).replace("_", "\\_") + ":%"),
    )
    return sorted({row["id"] for row in rows})


def _contains(path: Path, needle: bytes) -> bool:
    tail = b""
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK):
            if needle in tail + chunk:
                return True
            tail = chunk[-len(needle):]
    return False


def exported_copies(roots: Iterable[Path], sid: str) -> list[str]:
    """Files under NajdiLab's export/dataset roots that name this session.

    Every export's full archive and conversation records carry the external
    conversation id, so the session id is a reliable marker. Unreadable or
    over-limit trees fail closed (reported as a copy).
    """
    needle = sid.encode("ascii")
    found, seen = [], 0
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SCANNED_SUFFIXES:
                continue
            seen += 1
            if seen > SCAN_FILE_LIMIT:
                return found + [f"{root.name}/… (scan limit reached)"]
            try:
                if _contains(path, needle):
                    found.append(path.relative_to(root.parent).as_posix())
            except OSError:
                found.append(path.relative_to(root.parent).as_posix() + " (unreadable)")
    return found


def backups_after(root: Path | None, created_at: str) -> int:
    """Backups that may hold this conversation. Counted, never opened or changed."""
    if root is None or not Path(root).is_dir():
        return 0
    stamp = "".join(ch for ch in created_at if ch.isdigit())[:14]
    count = 0
    for path in Path(root).glob("najdilab-backup-*.zip"):
        digits = "".join(ch for ch in path.stem.removeprefix("najdilab-backup-") if ch.isdigit())[:14]
        count += not stamp or not digits or digits >= stamp
    return count


def plan(conn: sqlite3.Connection, row: dict, roots: Iterable[Path], backups: Path | None) -> dict:
    sid = row["id"]
    conversations = review_conversations(conn, sid)
    with_events, events = [], 0
    for cid in conversations:
        n = conn.execute(
            """SELECT COUNT(*) FROM review_events e JOIN reviews r ON r.id=e.review_id
               JOIN messages m ON m.id=r.message_id WHERE m.conversation_id=?""", (cid,)).fetchone()[0]
        if n:
            with_events.append(cid)
            events += n
    copies = exported_copies(roots, sid)
    return {
        "session_id": sid,
        "policy": POLICY,
        "confirmation": CONFIRMATION,
        "turns": conn.execute("SELECT COUNT(*) FROM chat_turns WHERE session_id=?", (sid,)).fetchone()[0],
        "requests": conn.execute("SELECT COUNT(*) FROM chat_requests WHERE session_id=?", (sid,)).fetchone()[0],
        "running": conn.execute("SELECT COUNT(*) FROM chat_requests WHERE session_id=? AND status='RUNNING'", (sid,)).fetchone()[0],
        "review_conversations": len(conversations),
        "review_conversations_to_redact": len(with_events),
        "review_events_retained": events,
        "exported_copies": copies,
        "backups_not_changed": backups_after(backups, row["created_at"]),
        "blocked": "EXPORTED" if copies else None,
    }


def execute(conn: sqlite3.Connection, row: dict, preview: dict) -> dict:
    """Runs inside the caller's BEGIN IMMEDIATE transaction; all or nothing."""
    sid = row["id"]
    conversations = review_conversations(conn, sid)
    redacted = deleted = 0
    now = utc_now()
    # Chat rows first: chat_turns references the review conversations.
    conn.execute("DELETE FROM chat_turns WHERE session_id=?", (sid,))
    conn.execute("DELETE FROM chat_requests WHERE session_id=?", (sid,))
    conn.execute("DELETE FROM chat_session_bindings WHERE session_id=?", (sid,))
    conn.execute("DELETE FROM chat_sessions WHERE id=?", (sid,))
    for cid in conversations:
        has_events = conn.execute(
            """SELECT 1 FROM review_events e JOIN reviews r ON r.id=e.review_id
               JOIN messages m ON m.id=r.message_id WHERE m.conversation_id=? LIMIT 1""", (cid,)).fetchone()
        if has_events:
            reviews = [r[0] for r in conn.execute(
                "SELECT r.id FROM reviews r JOIN messages m ON m.id=r.message_id WHERE m.conversation_id=?", (cid,))]
            conn.executemany("DELETE FROM review_tags WHERE review_id=?", [(r,) for r in reviews])
            conn.execute(
                """UPDATE reviews SET review_status='DELETED', original_response=?, corrected_response=NULL,
                   review_notes=NULL, training_eligible=0, exclude_from_training=1, ignored_reason=NULL,
                   deleted_at=COALESCE(deleted_at, ?), updated_at=?
                   WHERE message_id IN (SELECT id FROM messages WHERE conversation_id=?)""", (REDACTED, now, now, cid))
            conn.execute(
                """UPDATE messages SET content=?, metadata_json='{}', generation_settings_json='{}',
                   token_usage_json='{}', judge_result_json='{}', source_message_id=NULL WHERE conversation_id=?""",
                (REDACTED, cid))
            conn.execute(
                """UPDATE conversations SET external_conversation_id=?, title=?, metadata_json='{}',
                   model_version=NULL, updated_at=? WHERE id=?""", (f"deleted:{uuid4().hex}", REDACTED, now, cid))
            redacted += 1
        else:
            conn.execute("DELETE FROM conversations WHERE id=?", (cid,))
            deleted += 1
    conn.execute("INSERT INTO chat_deletions VALUES(?,?,?,?,?,?,?,?)",
                 (sid, now, POLICY, preview["turns"], preview["requests"], deleted, redacted, preview["review_events_retained"]))
    left = conn.execute(
        """SELECT (SELECT COUNT(*) FROM chat_turns WHERE session_id=:s) + (SELECT COUNT(*) FROM chat_requests WHERE session_id=:s)
           + (SELECT COUNT(*) FROM chat_sessions WHERE id=:s) + (SELECT COUNT(*) FROM conversations WHERE external_conversation_id LIKE :m)""",
        {"s": sid, "m": _marker(sid) + ":%"}).fetchone()[0]
    if left:
        raise IntegrationError("DELETE_INCOMPLETE", "Deletion could not remove every copy; nothing was changed.", 500)
    return {"review_conversations_deleted": deleted, "review_conversations_redacted": redacted}


def compact(path: Path) -> str:
    """Flush WAL frames that still hold old pages. Best effort; reports the outcome."""
    conn = sqlite3.connect(path, timeout=5, isolation_level=None)
    try:
        busy, _, _ = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        return "TRUNCATED" if busy == 0 else "BUSY"
    except sqlite3.Error:
        return "FAILED"
    finally:
        conn.close()
