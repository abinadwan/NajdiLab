-- Hugging Face Direct. Additive only: one new table for GGUF files that NajdiLab itself
-- downloaded into its managed folder. Files of Ollama, LM Studio or the owner's own folders
-- are never recorded here. A replay after the loader's commit/ledger gap stays idempotent.
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS managed_models (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    revision TEXT NOT NULL CHECK(length(revision) = 40),
    filename TEXT NOT NULL,
    relative_path TEXT NOT NULL UNIQUE,
    size_bytes INTEGER NOT NULL CHECK(size_bytes > 0),
    expected_sha256 TEXT NOT NULL CHECK(length(expected_sha256) = 64),
    verified_sha256 TEXT,
    status TEXT NOT NULL CHECK(status IN ('DOWNLOADING','PAUSED','READY','UNVERIFIED','ERROR')),
    error_code TEXT,
    license TEXT,
    architecture TEXT,
    quantization TEXT,
    model_max_context INTEGER,
    downloaded_bytes INTEGER NOT NULL DEFAULT 0 CHECK(downloaded_bytes >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    verified_at TEXT,
    UNIQUE(repo_id, revision, filename)
);
COMMIT;
