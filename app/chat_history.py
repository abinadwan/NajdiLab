"""Read-only, paged listing of saved chat sessions (UX-20).

Kept outside the protected chat workspace implementation: it only reads
`chat_sessions` and never changes session state.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .db import connect


def saved_sessions_page(db_path: Path | str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    conn = connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM chat_sessions WHERE status!='ARCHIVED'").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM chat_sessions WHERE status!='ARCHIVED' ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(row) for row in rows], total
    finally:
        conn.close()
