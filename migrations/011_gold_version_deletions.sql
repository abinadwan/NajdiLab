-- Retain dataset versions and export history while recording owned-file deletion.
CREATE TABLE gold_version_deletions (
    dataset_version_id INTEGER PRIMARY KEY REFERENCES dataset_versions(id),
    version TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('deleting', 'deleted')),
    original_path TEXT NOT NULL,
    quarantine_path TEXT NOT NULL UNIQUE,
    plan_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE gold_deletion_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_version_id INTEGER NOT NULL REFERENCES dataset_versions(id),
    version TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('started', 'failed', 'completed')),
    created_at TEXT NOT NULL,
    details_json TEXT NOT NULL
);
