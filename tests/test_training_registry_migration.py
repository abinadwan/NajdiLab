from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "plans" / "training-readiness" / "007_model_training_registry.sql"
ROLLBACK = ROOT / "plans" / "training-readiness" / "007_model_training_registry.rollback.sql"


def test_registry_migration_is_idempotent_and_integral(tmp_path: Path) -> None:
    database = tmp_path / "registry.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"model_registry", "training_jobs", "training_attempts"} <= names
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_registry_migration_rejects_invalid_state_and_rolls_back(tmp_path: Path) -> None:
    database = tmp_path / "registry.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        connection.execute("BEGIN")
        try:
            connection.execute(
                """INSERT INTO model_registry(
                    model_id,display_name,source_type,location,compatibility_json,
                    estimated_memory_json,measured_memory_json,availability,
                    validation_status,excluded,created_at,updated_at
                ) VALUES('fixture','Fixture','local','C:/fixture','{}','{}','{}',
                         'AVAILABLE','VALID',0,'now','now')"""
            )
            connection.execute(
                """INSERT INTO training_jobs(
                    job_id,status,model_id,model_fingerprint,dataset_version,
                    dataset_fingerprint,configuration_json,configuration_fingerprint,
                    environment_json,created_at,updated_at
                ) VALUES('job','SUCCESS','fixture',?,'dataset',?,'{}',?,'{}','now','now')""",
                ("a" * 64, "b" * 64, "c" * 64),
            )
        except sqlite3.IntegrityError:
            connection.rollback()
        else:
            raise AssertionError("invalid job state must fail closed")
        assert connection.execute("SELECT count(*) FROM model_registry").fetchone()[0] == 0


def test_registry_rollback_removes_only_prepared_tables(tmp_path: Path) -> None:
    database = tmp_path / "registry.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE preserved(id INTEGER PRIMARY KEY)")
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        connection.executescript(ROLLBACK.read_text(encoding="utf-8"))
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "preserved" in names
        assert not ({"model_registry", "training_jobs", "training_attempts"} & names)
