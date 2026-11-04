from __future__ import annotations

import hashlib
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


MIGRATION_REGISTRY_FILE = "registry.json"
_MIGRATION_NAME = re.compile(r"^\d{3}_[a-z0-9_]+\.sql$")
_MIGRATION_BLOCKED = re.compile(r"(rollback|revert|undo|down|helper|seed|fixture)", re.IGNORECASE)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TRANSACTION_KEYWORDS = {"BEGIN", "COMMIT", "END", "ROLLBACK", "SAVEPOINT", "RELEASE"}
_UNSUPPORTED_KEYWORDS = {"ATTACH", "DETACH", "VACUUM"}
_BEGIN_STATEMENT = re.compile(r"BEGIN(?:\s+(?:DEFERRED|IMMEDIATE|EXCLUSIVE))?(?:\s+TRANSACTION)?\s*;", re.IGNORECASE)
_COMMIT_STATEMENT = re.compile(r"(?:COMMIT|END)(?:\s+TRANSACTION)?\s*;", re.IGNORECASE)
_OUTSIDE_PRAGMA = re.compile(r"PRAGMA\s+foreign_keys\s*=\s*(?:ON|OFF)\s*;", re.IGNORECASE)


class MigrationFormError(RuntimeError):
    pass


class MigrationRegistryError(RuntimeError):
    pass


def migration_sha256(data: bytes) -> str:
    # Normalized like the cleanup inventory so a CRLF checkout on Windows matches.
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _without_leading_comments(text: str) -> str:
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
        elif text.startswith("--", index):
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline + 1
        elif text.startswith("/*", index):
            close = text.find("*/", index + 2)
            if close < 0:
                return ""
            index = close + 2
        else:
            break
    return text[index:]


def split_sql_statements(sql: str) -> list[str]:
    """Split on statement boundaries as SQLite's own parser sees them.

    sqlite3.complete_statement understands string literals, comments and trigger bodies,
    so a ";" inside any of those never ends a statement.
    """
    statements: list[str] = []
    start = 0
    for index, char in enumerate(sql):
        if char == ";" and sqlite3.complete_statement(sql[start:index + 1]):
            statement = sql[start:index + 1]
            if _without_leading_comments(statement).strip(" \t\r\n;"):
                statements.append(statement)
            start = index + 1
    if _without_leading_comments(sql[start:]).strip():
        raise MigrationFormError("the script ends with an incomplete statement")
    return statements


def _keyword(statement: str) -> str:
    match = re.match(r"[A-Za-z]+", _without_leading_comments(statement))
    return match.group(0).upper() if match else ""


def migration_plan(name: str, sql: str) -> tuple[list[str], list[str], list[str]]:
    """Return (prelude, body, trailer) statements, or refuse the migration.

    Accepted: optional `PRAGMA foreign_keys` statements, then either body statements alone
    or exactly `BEGIN ...; body; COMMIT;`, then optional `PRAGMA foreign_keys` statements.
    The loader runs the body and the ledger row in its own single transaction.
    """
    try:
        statements = split_sql_statements(sql)
    except MigrationFormError as exc:
        raise MigrationFormError(f"{name}: {exc}") from None
    kinds = [_keyword(statement) for statement in statements]
    core = [index for index, kind in enumerate(kinds) if kind != "PRAGMA"]
    if not core:
        raise MigrationFormError(f"{name}: no schema statements")
    for statement, kind in zip(statements, kinds):
        if kind in _UNSUPPORTED_KEYWORDS:
            raise MigrationFormError(f"{name}: {kind} is not supported in migrations")
        if kind == "PRAGMA" and not _OUTSIDE_PRAGMA.fullmatch(_without_leading_comments(statement).strip()):
            raise MigrationFormError(f"{name}: only PRAGMA foreign_keys is supported")
    first, last = core[0], core[-1]
    control = [index for index, kind in enumerate(kinds) if kind in _TRANSACTION_KEYWORDS]
    if control:
        if control != [first, last] or first == last:
            raise MigrationFormError(f"{name}: transaction statements are only supported as one leading BEGIN and one final COMMIT")
        if not _BEGIN_STATEMENT.fullmatch(_without_leading_comments(statements[first]).strip()):
            raise MigrationFormError(f"{name}: unsupported transaction start")
        if not _COMMIT_STATEMENT.fullmatch(_without_leading_comments(statements[last]).strip()):
            raise MigrationFormError(f"{name}: unsupported transaction end")
        first, last = first + 1, last - 1
    body = statements[first:last + 1]
    if not body:
        raise MigrationFormError(f"{name}: no schema statements")
    if any(_keyword(statement) == "PRAGMA" for statement in body):
        raise MigrationFormError(f"{name}: PRAGMA is only supported before or after the schema statements")
    prelude = statements[:core[0]]
    trailer = statements[core[-1] + 1:]
    return prelude, body, trailer


def load_migration_registry(directory: Path | None = None) -> dict[str, str]:
    """Approved forward migrations, in order, with their normalized SHA-256."""
    path = Path(directory or MIGRATIONS_DIR) / MIGRATION_REGISTRY_FILE
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise MigrationRegistryError(f"migration registry not found: {path}") from None
    except (OSError, ValueError) as exc:
        raise MigrationRegistryError(f"migration registry is unreadable: {exc}") from None
    entries = document.get("migrations") if isinstance(document, dict) else None
    if not isinstance(entries, list) or not entries or document.get("version") != 1:
        raise MigrationRegistryError("migration registry must be {\"version\": 1, \"migrations\": [...]}")
    registry: dict[str, str] = {}
    for entry in entries:
        name = entry.get("name") if isinstance(entry, dict) else None
        digest = entry.get("sha256") if isinstance(entry, dict) else None
        if not isinstance(name, str) or not _MIGRATION_NAME.fullmatch(name) or _MIGRATION_BLOCKED.search(name):
            raise MigrationRegistryError(f"invalid registered migration name: {name!r}")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise MigrationRegistryError(f"{name}: invalid sha256")
        if name in registry or (registry and name <= next(reversed(registry))):
            raise MigrationRegistryError(f"{name}: registry entries must be unique and in ascending order")
        registry[name] = digest
    return registry


def _approved_migration_sources() -> dict[str, str]:
    sources: dict[str, str] = {}
    for name, expected in load_migration_registry().items():
        path = MIGRATIONS_DIR / name
        if not path.is_file():
            raise MigrationRegistryError(f"{name}: registered migration file is missing")
        data = path.read_bytes()
        if migration_sha256(data) != expected:
            raise MigrationRegistryError(f"{name}: content does not match the reviewed registry hash")
        sources[name] = data.decode("utf-8")
    return sources


def _apply_migration(conn: sqlite3.Connection, name: str, sql: str) -> None:
    prelude, body, trailer = migration_plan(name, sql)
    try:
        for statement in prelude:
            conn.execute(statement)
        conn.execute("BEGIN IMMEDIATE")
        for statement in body:
            conn.execute(statement)
        conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (name, utc_now()))
        conn.execute("COMMIT")
        for statement in trailer:
            conn.execute(statement)
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def backup_before_migration(conn: sqlite3.Connection, db_path: Path, first_pending: str) -> Path:
    """A consistent copy of an existing database, written before its schema changes (V2.2.0).

    Schema changes are not automatically reversible; to undo an upgrade, stop NajdiLab and replace the
    database with this file (see docs/development/LANGUAGE_METADATA.md). Fresh databases have nothing
    to keep and are not copied.
    """
    folder = db_path.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = folder / f"{db_path.stem}-before-{first_pending.removesuffix('.sql')}-{stamp}.db"
    copy = sqlite3.connect(target)
    try:
        conn.backup(copy)
        if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("The pre-migration backup failed its integrity check; the database was not changed.")
    finally:
        copy.close()
    return target


def apply_migrations(db_path: Path | str = DB_PATH) -> None:
    """Apply registered migrations only (DB-01), each atomically with its ledger row (DB-02).

    Files in migrations/ that are not in registry.json are never read or executed.
    Every registered file must match its hash, and every pending migration must have a
    supported form, before the first pending migration runs.
    """
    sources = _approved_migration_sources()
    conn = connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        pending = [name for name in sources if name not in applied]
        for name in pending:
            migration_plan(name, sources[name])
        if pending and applied:
            backup_before_migration(conn, Path(db_path), pending[0])
        for name in pending:
            _apply_migration(conn, name, sources[name])
        conn.execute("PRAGMA optimize")
    finally:
        conn.close()


def rows_to_dicts(rows: list[sqlite3.Row] | sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]
