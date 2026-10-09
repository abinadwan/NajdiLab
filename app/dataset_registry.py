from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class RegistryConflict(RuntimeError):
    def __init__(self, conflicts: list[dict[str, Any]]):
        super().__init__("dataset registry contains unresolved conflicts")
        self.conflicts = conflicts


@dataclass(frozen=True)
class Discovery:
    version_id: str
    state: str
    path: str
    source: str
    manifest_sha256: str | None
    content_sha256: str
    record_count: int | None
    counts: dict[str, int]
    provenance: Any
    created_at: str | None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _content_hash(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in directory.iterdir() if p.is_file() and p.name != "manifest.json"):
        digest.update(path.name.encode("utf-8") + b"\0" + _sha256_file(path).encode("ascii") + b"\0")
    return digest.hexdigest()


def _state(value: Any) -> str:
    return {"draft": "Draft", "validated": "Validated", "frozen": "Frozen"}.get(
        str(value or "").strip().lower(), "Unknown"
    )


def _path_key(value: str) -> str:
    return os.path.normcase(os.path.normpath(value))


def _manifest(directory: Path) -> tuple[dict[str, Any] | None, str | None, list[dict[str, Any]]]:
    path = directory / "manifest.json"
    if not path.is_file():
        return None, None, [{"type": "MISSING_MANIFEST", "path": str(path)}]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, None, [{"type": "INVALID_MANIFEST", "path": str(path), "detail": type(exc).__name__}]
    if not isinstance(value, dict):
        return None, None, [{"type": "INVALID_MANIFEST", "path": str(path), "detail": "not_object"}]
    findings = []
    declared = value.get("sha256") or {}
    if isinstance(declared, dict):
        for name, expected in declared.items():
            candidate = directory / str(name)
            if not candidate.is_file():
                findings.append({"type": "MISSING_DECLARED_FILE", "path": str(candidate)})
            elif isinstance(expected, str) and len(expected) == 64 and _sha256_file(candidate) != expected:
                findings.append({"type": "DECLARED_HASH_MISMATCH", "path": str(candidate)})
    return value, _canonical_json_hash(value), findings


def discover(project: Path, db_path: Path) -> tuple[list[Discovery], list[dict[str, Any]]]:
    rows: list[Discovery] = []
    findings: list[dict[str, Any]] = []
    for source, root in (("exports", project / "exports"), ("datasets", project / "datasets")):
        if not root.is_dir():
            continue
        for directory in sorted(root.glob("gold-*")):
            if not directory.is_dir():
                continue
            manifest, manifest_hash, errors = _manifest(directory)
            findings.extend({**item, "version_id": directory.name} for item in errors)
            if manifest is None:
                continue
            counts = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
            counts = {str(k): int(v) for k, v in counts.items() if isinstance(v, int) and v >= 0}
            record_count = manifest.get("record_count")
            if not isinstance(record_count, int):
                record_count = sum(counts.values()) if counts else None
            rows.append(Discovery(
                directory.name, _state(manifest.get("state")), str(directory.resolve()), source,
                manifest_hash, _content_hash(directory), record_count, counts,
                manifest.get("provenance") or manifest.get("source_version") or manifest.get("source") or {},
                manifest.get("created_at"),
            ))
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        legacy = conn.execute(
            "SELECT version, export_path, manifest_json, record_count, created_at FROM dataset_versions"
        ).fetchall()
    for version, export_path, manifest_json, record_count, created_at in legacy:
        try:
            manifest = json.loads(manifest_json or "{}")
        except json.JSONDecodeError:
            findings.append({"type": "INVALID_LEGACY_MANIFEST", "version_id": str(version)})
            continue
        path = Path(str(export_path)).resolve()
        if not path.is_dir():
            findings.append({"type": "MISSING_LEGACY_PATH", "version_id": str(version), "path": str(path)})
            continue
        rows.append(Discovery(
            str(version), _state(manifest.get("state")), str(path), "sqlite_legacy",
            _canonical_json_hash(manifest) if manifest else None, _content_hash(path), record_count,
            manifest.get("files") if isinstance(manifest.get("files"), dict) else {},
            manifest.get("provenance") or manifest.get("source_version") or manifest.get("source") or {}, created_at,
        ))
    return rows, findings


def build_plan(rows: Iterable[Discovery], blocking_findings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    conflicts = list(blocking_findings or [])
    by_version: dict[str, list[Discovery]] = defaultdict(list)
    by_path: dict[str, list[Discovery]] = defaultdict(list)
    for row in rows:
        by_version[row.version_id].append(row)
        by_path[_path_key(row.path)].append(row)
    for key, items in by_path.items():
        ids = sorted({item.version_id for item in items})
        if len(ids) > 1:
            conflicts.append({"type": "PATH_MULTIPLE_VERSION_IDS", "path_key": key, "version_ids": ids})
    versions, locations = [], []
    for version_id, items in sorted(by_version.items()):
        paths = sorted({_path_key(item.path) for item in items})
        manifests = sorted({item.manifest_sha256 for item in items if item.manifest_sha256})
        contents = sorted({item.content_sha256 for item in items})
        counts = sorted({item.record_count for item in items if item.record_count is not None})
        for kind, values in (("VERSION_MULTIPLE_PATHS", paths), ("VERSION_MANIFEST_MISMATCH", manifests),
                             ("VERSION_CONTENT_MISMATCH", contents), ("VERSION_COUNT_MISMATCH", counts)):
            if len(values) > 1:
                conflicts.append({"type": kind, "version_id": version_id, "values": values})
        preferred = next((item for item in items if item.source != "sqlite_legacy"), items[0])
        states = sorted({item.state for item in items if item.state != "Unknown"})
        if len(states) > 1:
            conflicts.append({"type": "VERSION_STATE_MISMATCH", "version_id": version_id, "values": states})
        versions.append({
            "version_id": version_id, "state": states[0] if states else "Unknown",
            "manifest_sha256": preferred.manifest_sha256, "content_sha256": preferred.content_sha256,
            "record_count": counts[0] if len(counts) == 1 else preferred.record_count,
            "counts": preferred.counts, "provenance": preferred.provenance, "created_at": preferred.created_at,
        })
        grouped: dict[str, list[Discovery]] = defaultdict(list)
        for item in items:
            grouped[_path_key(item.path)].append(item)
        for key, same_path in grouped.items():
            locations.append({
                "version_id": version_id, "canonical_path": same_path[0].path, "path_key": key,
                "sources": sorted({item.source for item in same_path}),
                "manifest_sha256": preferred.manifest_sha256, "content_sha256": preferred.content_sha256,
            })
    return {"versions": versions, "locations": locations, "conflicts": conflicts}


def apply_plan(conn: sqlite3.Connection, plan: dict[str, Any], schema_sql: str) -> dict[str, int]:
    if plan["conflicts"]:
        raise RegistryConflict(plan["conflicts"])
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("BEGIN IMMEDIATE")
    try:
        for statement in schema_sql.split(";"):
            if statement.strip():
                conn.execute(statement)
        stamp = _utc_now()
        for row in plan["versions"]:
            conn.execute(
                "INSERT INTO dataset_registry_versions VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(version_id) DO UPDATE SET state=excluded.state,manifest_sha256=excluded.manifest_sha256,"
                "content_sha256=excluded.content_sha256,record_count=excluded.record_count,counts_json=excluded.counts_json,"
                "provenance_json=excluded.provenance_json,created_at=excluded.created_at,discovered_at=excluded.discovered_at "
                "WHERE state IS NOT excluded.state OR manifest_sha256 IS NOT excluded.manifest_sha256 OR "
                "content_sha256 IS NOT excluded.content_sha256 OR record_count IS NOT excluded.record_count OR "
                "counts_json IS NOT excluded.counts_json OR provenance_json IS NOT excluded.provenance_json OR created_at IS NOT excluded.created_at",
                (row["version_id"], row["state"], row["manifest_sha256"], row["content_sha256"], row["record_count"],
                 json.dumps(row["counts"], ensure_ascii=False, sort_keys=True),
                 json.dumps(row["provenance"], ensure_ascii=False, sort_keys=True), row["created_at"], stamp),
            )
        for row in plan["locations"]:
            conn.execute(
                "INSERT INTO dataset_registry_locations(version_id,canonical_path,path_key,sources_json,manifest_sha256,content_sha256,discovered_at) "
                "VALUES (?,?,?,?,?,?,?) ON CONFLICT(path_key) DO UPDATE SET sources_json=excluded.sources_json,"
                "manifest_sha256=excluded.manifest_sha256,content_sha256=excluded.content_sha256,discovered_at=excluded.discovered_at "
                "WHERE version_id IS NOT excluded.version_id OR canonical_path IS NOT excluded.canonical_path OR "
                "sources_json IS NOT excluded.sources_json OR manifest_sha256 IS NOT excluded.manifest_sha256 OR content_sha256 IS NOT excluded.content_sha256",
                (row["version_id"], row["canonical_path"], row["path_key"],
                 json.dumps(row["sources"], ensure_ascii=False), row["manifest_sha256"], row["content_sha256"], stamp),
            )
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("foreign_key_check failed")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "versions": conn.execute("SELECT count(*) FROM dataset_registry_versions").fetchone()[0],
        "locations": conn.execute("SELECT count(*) FROM dataset_registry_locations").fetchone()[0],
    }

