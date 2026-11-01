from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "najdilab.db"
MIGRATIONS_DIR = ROOT / "migrations"

SECRET_KEY_PATTERN = re.compile(
    r"(api[_-]?key|authorization|password|passwd|secret|token|access[_-]?key|private[_-]?key|cookie)",
    re.IGNORECASE,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return {} if fallback is None else fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {} if fallback is None else fallback


def redact_secrets(value: Any) -> Any:
    """Remove common credentials recursively before anything reaches SQLite."""
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if SECRET_KEY_PATTERN.search(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()


def backup_db(db_path: Path | str = DB_PATH, dest_path: Path | str | None = None) -> Path:
    """Online backup using SQLite's hot-backup API.

    Backup boundary: ``data/najdilab.db`` holds ALL application state —
    reviews, manual data, conversations, schema_migrations, and dataset_versions.
    Frozen export files in ``exports/`` are derived from the DB and must also be
    backed up to restore a complete working state, but the DB alone is sufficient
    to re-derive them.  Migrations are source-controlled and do not need backup.

    Recovery: restore the ``.db`` file then call ``apply_migrations`` (idempotent).
    """
    src = Path(db_path)
    if dest_path is None:
        dest_path = src.with_suffix(f".backup{utc_now().replace(':', '-').replace('.', '-')}.db")
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src_conn = connect(src)
    dest_conn = sqlite3.connect(dest)
    try:
        src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()
    return dest


def apply_migrations(db_path: Path | str = DB_PATH) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            # DB-01: skip rollback/helper files — only apply numbered migration files
            if not re.fullmatch(r"\d{3}_[a-z0-9_]+\.sql", migration.name):
                continue
            if migration.name in applied:
                continue
            sql = migration.read_text(encoding="utf-8")
            now = utc_now()
            ledger = (
                f"INSERT INTO schema_migrations(version, applied_at)"
                f" VALUES ('{migration.name}', '{now}');"
            )
            # DB-02: make the migration DDL and ledger INSERT atomic so a crash between
            # them cannot leave the schema changed with no ledger entry.
            # Migrations that already wrap themselves in BEGIN...COMMIT get the INSERT
            # injected before their final COMMIT. Others are wrapped in a new transaction.
            if re.search(r"^COMMIT\s*;", sql, re.MULTILINE | re.IGNORECASE):
                parts = re.split(r"(?im)(^COMMIT\s*;)", sql, maxsplit=1)
                combined = parts[0] + ledger + "\n" + parts[1]
            else:
                combined = "BEGIN;\n" + sql.rstrip("\n") + "\n" + ledger + "\nCOMMIT;\n"
            conn.executescript(combined)
        conn.execute("PRAGMA optimize")
    finally:
        conn.close()


def rows_to_dicts(rows: list[sqlite3.Row] | sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]
