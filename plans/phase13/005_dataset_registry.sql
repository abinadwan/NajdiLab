PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dataset_registry_versions (
    version_id TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK (state IN ('Draft', 'Validated', 'Frozen', 'Unknown')),
    manifest_sha256 TEXT,
    content_sha256 TEXT NOT NULL,
    record_count INTEGER CHECK (record_count IS NULL OR record_count >= 0),
    counts_json TEXT NOT NULL DEFAULT '{}',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT,
    discovered_at TEXT NOT NULL,
    CHECK (manifest_sha256 IS NULL OR length(manifest_sha256) = 64),
    CHECK (length(content_sha256) = 64),
    CHECK (json_valid(counts_json)),
    CHECK (json_valid(provenance_json))
);

CREATE TABLE IF NOT EXISTS dataset_registry_locations (
    id INTEGER PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES dataset_registry_versions(version_id) ON DELETE RESTRICT,
    canonical_path TEXT NOT NULL,
    path_key TEXT NOT NULL UNIQUE,
    sources_json TEXT NOT NULL,
    manifest_sha256 TEXT,
    content_sha256 TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    UNIQUE (version_id, path_key),
    CHECK (json_valid(sources_json)),
    CHECK (manifest_sha256 IS NULL OR length(manifest_sha256) = 64),
    CHECK (length(content_sha256) = 64)
);

CREATE INDEX IF NOT EXISTS idx_dataset_registry_locations_version
ON dataset_registry_locations(version_id);

