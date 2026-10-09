import json
import sqlite3
from pathlib import Path

import pytest

from app.dataset_registry import Discovery, RegistryConflict, apply_plan, build_plan, discover


SCHEMA = (Path(__file__).resolve().parents[1] / "plans" / "phase13" / "005_dataset_registry.sql").read_text(encoding="utf-8")


def row(tmp_path, version="gold-v001", name="one", manifest="a", content="b"):
    return Discovery(version, "Frozen", str(tmp_path / name), "exports", manifest * 64, content * 64,
                     1, {"sft.jsonl": 1}, {}, None)


def test_idempotent_backfill(tmp_path):
    db = tmp_path / "test.db"
    plan = build_plan([row(tmp_path)])
    with sqlite3.connect(db) as conn:
        assert apply_plan(conn, plan, SCHEMA) == {"versions": 1, "locations": 1}
        before = conn.total_changes
        assert apply_plan(conn, plan, SCHEMA) == {"versions": 1, "locations": 1}
        assert conn.total_changes == before


def test_path_collision_blocks_and_rolls_back(tmp_path):
    db = tmp_path / "test.db"
    clean = build_plan([row(tmp_path)])
    with sqlite3.connect(db) as conn:
        apply_plan(conn, clean, SCHEMA)
        before = conn.execute("SELECT count(*) FROM dataset_registry_versions").fetchone()[0]
        conflict = build_plan([row(tmp_path), row(tmp_path, version="gold-v002")])
        with pytest.raises(RegistryConflict):
            apply_plan(conn, conflict, SCHEMA)
        assert conn.execute("SELECT count(*) FROM dataset_registry_versions").fetchone()[0] == before


@pytest.mark.parametrize("field,value", [("manifest_sha256", "c" * 64), ("content_sha256", "d" * 64)])
def test_same_id_with_different_evidence_blocks(tmp_path, field, value):
    first = row(tmp_path)
    values = first.__dict__ | {"path": str(tmp_path / "two"), field: value}
    plan = build_plan([first, Discovery(**values)])
    assert plan["conflicts"]


def test_invalid_manifest_and_missing_declared_file_are_blocking(tmp_path):
    project = tmp_path
    version = project / "exports" / "gold-bad"
    version.mkdir(parents=True)
    (version / "manifest.json").write_text("{bad", encoding="utf-8")
    db = project / "db.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE dataset_versions(version TEXT,export_path TEXT,manifest_json TEXT,record_count INTEGER,created_at TEXT)")
    rows, findings = discover(project, db)
    assert rows == []
    assert findings[0]["type"] == "INVALID_MANIFEST"
    (version / "manifest.json").write_text(json.dumps({"sha256": {"sft.jsonl": "0" * 64}}), encoding="utf-8")
    _, findings = discover(project, db)
    assert any(item["type"] == "MISSING_DECLARED_FILE" for item in findings)


def test_foreign_keys_and_uniqueness(tmp_path):
    db = tmp_path / "test.db"
    with sqlite3.connect(db) as conn:
        apply_plan(conn, build_plan([row(tmp_path)]), SCHEMA)
        conn.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO dataset_registry_locations(version_id,canonical_path,path_key,sources_json,content_sha256,discovered_at) VALUES('missing','x','x','[]',?, 'now')", ("a" * 64,))


def test_constraint_failure_rolls_back_schema_and_rows(tmp_path):
    db = tmp_path / "test.db"
    plan = build_plan([row(tmp_path)])
    plan["versions"][0]["content_sha256"] = None
    with sqlite3.connect(db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            apply_plan(conn, plan, SCHEMA)
        assert conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'dataset_registry_%'").fetchall() == []

