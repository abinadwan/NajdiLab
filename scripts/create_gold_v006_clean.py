from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(path: Path) -> tuple[str, dict[str, str]]:
    files = {p.relative_to(path).as_posix(): sha256(p) for p in sorted(path.rglob("*")) if p.is_file()}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return digest, files


def rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]


def manual_export_rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    result = []
    query = (
        f"SELECT * FROM {table} WHERE training_eligible=1 AND evaluation_only=0 "
        "AND archived=0 AND exclude_from_training=0 AND ignored_at IS NULL "
        "AND deleted_at IS NULL AND demo=0 ORDER BY id"
    )
    for raw in conn.execute(query):
        item = dict(raw)
        item["id"] = f"{table}:{raw['id']}"
        for key in ("messages_json", "prompt_context_json", "metadata_json"):
            if key in item:
                value = item.pop(key)
                item[key.removesuffix("_json")] = json.loads(value or "{}")
        result.append(item)
    return result


def write_jsonl(path: Path, values: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def build_source_snapshot(db_path: Path, target: Path) -> dict:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("database integrity check failed")
        archive = {
            "conversations": rows(conn, "conversations"),
            "messages": rows(conn, "messages"),
            "reviews": rows(conn, "reviews"),
            "review_tags": [dict(row) for row in conn.execute("SELECT * FROM review_tags ORDER BY review_id, tag")],
            "manual_sft_items": rows(conn, "manual_sft_items"),
            "direct_language_texts": rows(conn, "direct_language_texts"),
            "preference_pairs": rows(conn, "preference_pairs"),
        }
        direct = manual_export_rows(conn, "direct_language_texts")
        preference = manual_export_rows(conn, "preference_pairs")
        counts = {
            "conversations": len(archive["conversations"]),
            "messages": len(archive["messages"]),
            "reviews": len(archive["reviews"]),
            "active_review_statuses": {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT review_status, COUNT(*) FROM reviews WHERE review_status NOT IN ('DELETED','IGNORED') GROUP BY review_status"
                )
            },
        }
    finally:
        conn.close()
    target.mkdir(parents=True, exist_ok=True)
    (target / "full_archive.json").write_text(json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_jsonl(target / "direct_language.jsonl", direct)
    write_jsonl(target / "preference_pairs.jsonl", preference)
    (target / "manifest.json").write_text(
        json.dumps({"version": "live-read-only-snapshot", "evaluation_split": {}, "counts": counts}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Build gold-v006-clean without writing NajdiLab SQLite")
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    db_path = root / "data" / "najdilab.db"
    output = root / "exports" / "gold-v006-clean"
    eval_output = root / "reports" / "eval-v006-clean"
    if output.exists() or eval_output.exists():
        raise FileExistsError("gold-v006-clean or eval-v006-clean already exists")

    protected = {}
    for name in ("gold-v004", "gold-v005-clean"):
        protected[name] = tree_hash(root / "exports" / name)
    db_before = sha256(db_path)

    staging_parent = root / "exports"
    snapshot = Path(tempfile.mkdtemp(prefix=".gold-v006-source-", dir=staging_parent))
    try:
        counts = build_source_snapshot(db_path, snapshot)
        from app.clean_export import create_clean_export
        result = create_clean_export(
            snapshot, output, eval_output, version="gold-v006-clean"
        )
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)

    protected_after = {name: tree_hash(root / "exports" / name) for name in protected}
    db_after = sha256(db_path)
    audit = {
        "database_sha256_before": db_before,
        "database_sha256_after": db_after,
        "database_unchanged": db_before == db_after,
        "protected_exports": {
            name: {
                "tree_sha256_before": protected[name][0],
                "tree_sha256_after": protected_after[name][0],
                "unchanged": protected[name][0] == protected_after[name][0],
            }
            for name in protected
        },
        "snapshot_counts": counts,
        "manifest": result["manifest"],
        "clean_context_report": result["clean_context_report"],
    }
    (output / "final_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
