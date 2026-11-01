from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from .db import DB_PATH, ROOT


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None




def dataset_catalog(root: Path = ROOT, db_path: Path = DB_PATH) -> dict[str, Any]:
    """Join filesystem and SQLite registrations without mutating either source."""
    records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source, base in (("exports", root / "exports"), ("datasets", root / "datasets")):
        if not base.is_dir():
            continue
        for path in sorted(base.glob("gold-*")):
            if not path.is_dir():
                continue
            manifest = _read_json(path / "manifest.json")
            records[path.name].append({"source": source, "path": str(path), "state": (manifest or {}).get("state") or "UNKNOWN", "manifest": "valid" if manifest else "missing_or_invalid"})
    try:
        uri = f"file:{Path(db_path).resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            for version, export_path, manifest_json in conn.execute("SELECT version, export_path, manifest_json FROM dataset_versions"):
                try:
                    manifest = json.loads(manifest_json or "{}")
                except ValueError:
                    manifest = {}
                records[str(version)].append({"source": "sqlite", "path": str(export_path), "state": manifest.get("state") or "UNKNOWN", "manifest": "valid" if manifest else "missing_or_invalid"})
    except (sqlite3.Error, OSError) as exc:
        db_error = type(exc).__name__
    else:
        db_error = None
    items = []
    for version, sources in sorted(records.items(), reverse=True):
        fs_paths = {s["path"].lower() for s in sources if s["source"] != "sqlite"}
        db_paths = {s["path"].lower() for s in sources if s["source"] == "sqlite"}
        duplicate_fs = len(fs_paths) > 1
        path_conflict = bool(fs_paths and db_paths and not (fs_paths & db_paths))
        items.append({"version": version, "sources": sources, "conflict": duplicate_fs or path_conflict, "conflict_reasons": (["DUPLICATE_FILESYSTEM_ID"] if duplicate_fs else []) + (["SQLITE_PATH_MISMATCH"] if path_conflict else [])})
    return {"items": items, "conflicts": [i["version"] for i in items if i["conflict"]], "db_error": db_error, "read_only": True}
