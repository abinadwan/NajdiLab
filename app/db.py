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
    """Write a verified, consistent snapshot of the SQLite database to a new file.

    Scope: every table in the database file (conversations, reviews, review_events,
    review_event_baseline, manual data and versions, schema_migrations). Not covered:
    exports/ and datasets/ — frozen exports are not re-derivable from the database.
    scripts/backup.py bundles this snapshot with exports/; restore procedure and limits
    are in docs/backup-and-restore.md.
    """
    src = Path(db_path)
    if not src.is_file():
        raise FileNotFoundError(f"database not found: {src}")
    if dest_path is None:
        stamp = utc_now().replace(":", "").replace("-", "").replace(".", "")
        dest_path = src.with_name(f"{src.stem}.backup-{stamp}.db")
    dest = Path(dest_path)
    if dest.exists():
        raise FileExistsError(f"backup target already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{src.resolve().as_posix()}?mode=ro", uri=True)
    destination = sqlite3.connect(dest)
    try:
        source.backup(destination)
        if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("backup failed integrity_check")
    except BaseException:
        destination.close()
        dest.unlink(missing_ok=True)
        raise
    finally:
        destination.close()
        source.close()
    return dest


_MIGRATION_NAME = re.compile(r"^\d{3}_[a-z0-9_]+\.sql$")
# DB-01: explicit blocklist — numeric prefix alone is not sufficient; a file named
# 007_rollback.sql would still match the pattern without this secondary check.
_MIGRATION_BLOCKED = re.compile(
    r"(rollback|revert|undo|down|helper|seed|fixture)", re.IGNORECASE
)


class MigrationFormError(RuntimeError):
    pass


# Trigger bodies use "BEGIN ... END;" without a semicolon after BEGIN, and are never matched.
_TX_BEGIN = re.compile(r"^[ \t]*BEGIN(?:[ \t]+(?:DEFERRED|IMMEDIATE|EXCLUSIVE))?(?:[ \t]+TRANSACTION)?[ \t]*;[ \t]*$", re.I | re.M)
_TX_COMMIT = re.compile(r"^[ \t]*COMMIT(?:[ \t]+TRANSACTION)?[ \t]*;[ \t]*$", re.I | re.M)
_TX_UNSUPPORTED = re.compile(r"^[ \t]*(?:ROLLBACK|SAVEPOINT|RELEASE|END[ \t]+TRANSACTION)\b", re.I | re.M)
_PRAGMA_LINE = re.compile(r"^[ \t]*PRAGMA[ \t]+\w+[ \t]*(?:=[ \t]*\w+)?[ \t]*;[ \t]*$", re.I)


def _outside_tx_allowed(text: str) -> bool:
    return all(
        not line.strip() or line.lstrip().startswith("--") or _PRAGMA_LINE.match(line)
        for line in text.splitlines()
    )


def atomic_migration_script(name: str, sql: str, applied_at: str) -> str:
    """Return a script that applies the migration and its ledger row in one transaction.

    Supported forms: (a) no transaction statements, optionally preceded by PRAGMA lines;
    (b) exactly one BEGIN and one COMMIT with only PRAGMA lines or comments outside them.
    Anything else raises MigrationFormError before any statement runs.
    """
    if not _MIGRATION_NAME.fullmatch(name):
        raise MigrationFormError(f"{name}: invalid migration name")
    ledger = f"INSERT INTO schema_migrations(version, applied_at) VALUES ('{name}', '{applied_at}');"
    if _TX_UNSUPPORTED.search(sql):
        raise MigrationFormError(f"{name}: ROLLBACK/SAVEPOINT/RELEASE/END TRANSACTION are not supported")
    begins = list(_TX_BEGIN.finditer(sql))
    commits = list(_TX_COMMIT.finditer(sql))
    if not begins and not commits:
        lines = sql.splitlines(keepends=True)
        split = 0
        while split < len(lines) and _outside_tx_allowed(lines[split]):
            split += 1
        prelude, body = "".join(lines[:split]), "".join(lines[split:])
        return f"{prelude}BEGIN IMMEDIATE;\n{body.rstrip()}\n{ledger}\nCOMMIT;\n"
    if len(begins) == 1 and len(commits) == 1 and begins[0].end() <= commits[0].start():
        if not _outside_tx_allowed(sql[:begins[0].start()]) or not _outside_tx_allowed(sql[commits[0].end():]):
            raise MigrationFormError(f"{name}: only PRAGMA statements may appear outside BEGIN/COMMIT")
        cut = commits[0].start()
        return f"{sql[:cut]}{ledger}\n{sql[cut:]}"
    raise MigrationFormError(f"{name}: expected zero or exactly one BEGIN/COMMIT pair")


def _pending_migrations(applied: set[str]) -> list[Path]:
    return [
        path for path in sorted(MIGRATIONS_DIR.glob("*.sql"))
        if _MIGRATION_NAME.fullmatch(path.name)
        and not _MIGRATION_BLOCKED.search(path.name)
        and path.name not in applied
    ]


def apply_migrations(db_path: Path | str = DB_PATH) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        pending = _pending_migrations(applied)
        sources = {path.name: path.read_text(encoding="utf-8") for path in pending}
        # Reject unsupported forms before anything runs, so a bad later file cannot
        # leave earlier pending migrations half-applied relative to the release.
        for name, sql in sources.items():
            atomic_migration_script(name, sql, "validation")
        for name, sql in sources.items():
            script = atomic_migration_script(name, sql, utc_now())
            try:
                conn.executescript(script)
            except BaseException:
                if conn.in_transaction:
                    conn.rollback()
                raise
        conn.execute("PRAGMA optimize")
    finally:
        conn.close()


def rows_to_dicts(rows: list[sqlite3.Row] | sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]
