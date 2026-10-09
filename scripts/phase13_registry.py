from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.dataset_registry import RegistryConflict, apply_plan, build_plan, discover

SCHEMA = ROOT / "plans" / "phase13" / "005_dataset_registry.sql"
PRODUCTION_DB = ROOT / "data" / "najdilab.db"
APPROVAL_TOKEN = "REG-09-APPROVED"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup(source: Path, target: Path) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True, timeout=30) as src:
        dst = sqlite3.connect(target)
        try:
            src.execute("PRAGMA busy_timeout=30000")
            src.backup(dst, pages=256)
        finally:
            dst.close()
    restored = target.with_name(target.stem + "-restore-proof.db")
    with sqlite3.connect(f"file:{target.resolve().as_posix()}?mode=ro", uri=True) as saved:
        restored_conn = sqlite3.connect(restored)
        try:
            saved.backup(restored_conn)
        finally:
            restored_conn.close()
    with sqlite3.connect(restored) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
    return {"backup": str(target), "restore_proof": str(restored), "sha256": sha256(target),
            "integrity": integrity, "foreign_key_errors": len(foreign_keys)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1.3 guarded dataset-registry runner")
    parser.add_argument("mode", choices=("preflight", "prepare", "rehearse", "execute"), default="preflight", nargs="?")
    parser.add_argument("--project", type=Path, default=ROOT)
    parser.add_argument("--database", type=Path, default=PRODUCTION_DB)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--approval-token")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    project, database = args.project.resolve(), args.database.resolve()
    rows, findings = discover(project, database)
    plan = build_plan(rows, findings)
    result = {"mode": args.mode, "project": str(project), "database": str(database),
              "source_rows": len(rows), "versions": len(plan["versions"]),
              "locations": len(plan["locations"]), "conflicts": plan["conflicts"]}
    if args.mode == "prepare":
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = (args.backup or (project / "backups" / f"phase13-pre-migration-{stamp}.db")).resolve()
        result["backup"] = backup(database, target)
    elif args.mode == "rehearse":
        if database == PRODUCTION_DB.resolve():
            raise SystemExit("rehearse refuses the production database")
        conn = sqlite3.connect(database, timeout=30)
        try:
            before = conn.total_changes
            first = apply_plan(conn, plan, SCHEMA.read_text(encoding="utf-8"))
            first_changes = conn.total_changes - before
            before_second = conn.total_changes
            second = apply_plan(conn, plan, SCHEMA.read_text(encoding="utf-8"))
            result["rehearsal"] = {
                "first": first, "first_changes": first_changes, "second": second,
                "second_changes": conn.total_changes - before_second,
                "integrity": conn.execute("PRAGMA integrity_check").fetchone()[0],
                "foreign_key_errors": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
            }
        finally:
            conn.close()
    elif args.mode == "execute":
        if database != PRODUCTION_DB.resolve():
            raise SystemExit("execute is reserved for the configured production database")
        if args.approval_token != APPROVAL_TOKEN:
            raise SystemExit("REG-09 is blocked: explicit production approval token is required")
        if args.backup is None or not args.backup.is_file():
            raise SystemExit("a verified pre-migration backup is required")
        if plan["conflicts"]:
            raise RegistryConflict(plan["conflicts"])
        conn = sqlite3.connect(database, timeout=30)
        try:
            result["applied"] = apply_plan(conn, plan, SCHEMA.read_text(encoding="utf-8"))
            result["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 2 if plan["conflicts"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

