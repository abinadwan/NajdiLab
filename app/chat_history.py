"""Read-only, paged listing of saved chat sessions (UX-20, Chat V2).

Kept outside the protected chat workspace implementation: it only reads
chat tables and never changes session state. Titles are suggested locally
from the first message; nothing is sent to any model or service.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .db import connect

TITLE_LIMIT = 60
_MARKUP = re.compile(r"^[\s#>*`~\-+|]+|[*`~|]+")
_SPACE = re.compile(r"\s+")


def suggest_title(text: Any) -> str | None:
    """Local, deterministic title from a message: first non-empty line, markup
    stripped, cut at a word boundary. Returns None for text with no words."""
    if not isinstance(text, str):
        return None
    for line in text.splitlines():
        line = _SPACE.sub(" ", _MARKUP.sub("", line)).strip()
        if line:
            break
    else:
        return None
    if len(line) <= TITLE_LIMIT:
        return line
    cut = line[:TITLE_LIMIT]
    space = cut.rfind(" ")
    if space >= TITLE_LIMIT // 2:
        cut = cut[:space]
    return cut.rstrip(" ,.;:،؛") + "…"


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def saved_sessions_page(db_path: Path | str, limit: int, offset: int, *, query: str = "",
                        archived: bool = False) -> tuple[list[dict[str, Any]], int]:
    """Pinned first, then most recent activity. `archived` lists only archived
    conversations; the default excludes them (the pre-V2 contract)."""
    query = query.strip() if isinstance(query, str) else ""
    if len(query) > 200:
        query = query[:200]
    where = ["s.status " + ("= 'ARCHIVED'" if archived else "!= 'ARCHIVED'")]
    params: list[Any] = []
    if query:
        where.append("""(s.title LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM chat_turns t WHERE t.session_id = s.id
                         AND (t.user_content LIKE ? ESCAPE '\\' OR t.assistant_content LIKE ? ESCAPE '\\')))""")
        params += [_like(query)] * 3
    clause = " AND ".join(where)
    conn = connect(db_path)
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM chat_sessions s WHERE {clause}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT s.*, (SELECT COUNT(*) FROM chat_turns t WHERE t.session_id = s.id) AS turn_count,
                       (SELECT t.user_content FROM chat_turns t WHERE t.session_id = s.id ORDER BY t.ordinal LIMIT 1) AS first_user
                FROM chat_sessions s WHERE {clause}
                ORDER BY (s.pinned_at IS NULL), s.pinned_at DESC, COALESCE(s.last_activity_at, s.updated_at) DESC, s.id DESC LIMIT ? OFFSET ?""",
            (*params, limit, offset),
        )
        items = []
        for row in rows:
            item = dict(row)
            first = item.pop("first_user")
            # A stored title wins; otherwise a display-only suggestion, never saved here.
            item["display_title"] = item["title"] or suggest_title(first)
            item["title_derived"] = item["title"] is None and item["display_title"] is not None
            items.append(item)
        return items, total
    finally:
        conn.close()
