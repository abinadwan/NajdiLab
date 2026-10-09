PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS model_registry (
    model_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('local', 'huggingface', 'ollama')),
    provider TEXT,
    location TEXT NOT NULL,
    revision TEXT,
    architecture TEXT,
    parameter_count INTEGER CHECK (parameter_count IS NULL OR parameter_count > 0),
    precision TEXT,
    quantization TEXT,
    weight_format TEXT,
    tokenizer_available INTEGER CHECK (tokenizer_available IN (0, 1) OR tokenizer_available IS NULL),
    compatibility_json TEXT NOT NULL DEFAULT '{}',
    estimated_memory_json TEXT NOT NULL DEFAULT '{}',
    measured_memory_json TEXT NOT NULL DEFAULT '{}',
    model_fingerprint TEXT,
    availability TEXT NOT NULL DEFAULT 'NOT_CHECKED',
    validation_status TEXT NOT NULL DEFAULT 'NOT_CHECKED',
    excluded INTEGER NOT NULL DEFAULT 0 CHECK (excluded IN (0, 1)),
    exclusion_reason TEXT,
    last_verified_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (json_valid(compatibility_json)),
    CHECK (json_valid(estimated_memory_json)),
    CHECK (json_valid(measured_memory_json)),
    CHECK (model_fingerprint IS NULL OR length(model_fingerprint) = 64)
);

CREATE TABLE IF NOT EXISTS training_jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'VALIDATING', 'READY', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    model_id TEXT NOT NULL REFERENCES model_registry(model_id) ON DELETE RESTRICT,
    model_revision TEXT,
    model_fingerprint TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    dataset_fingerprint TEXT NOT NULL,
    configuration_json TEXT NOT NULL,
    configuration_fingerprint TEXT NOT NULL,
    environment_json TEXT NOT NULL DEFAULT '{}',
    output_path TEXT,
    error_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    CHECK (length(model_fingerprint) = 64),
    CHECK (length(dataset_fingerprint) = 64),
    CHECK (length(configuration_fingerprint) = 64),
    CHECK (json_valid(configuration_json)),
    CHECK (json_valid(environment_json)),
    CHECK (error_json IS NULL OR json_valid(error_json))
);

CREATE TABLE IF NOT EXISTS training_attempts (
    attempt_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES training_jobs(job_id) ON DELETE RESTRICT,
    attempt_type TEXT NOT NULL CHECK (attempt_type IN ('DRY_RUN', 'SMOKE', 'FULL')),
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'VALIDATING', 'READY', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    execution_manifest_json TEXT NOT NULL,
    environment_snapshot_json TEXT NOT NULL DEFAULT '{}',
    output_path TEXT,
    log_path TEXT,
    error_json TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    CHECK (json_valid(execution_manifest_json)),
    CHECK (json_valid(environment_snapshot_json)),
    CHECK (error_json IS NULL OR json_valid(error_json))
);

CREATE INDEX IF NOT EXISTS idx_training_jobs_status ON training_jobs(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_training_attempts_job ON training_attempts(job_id, created_at);
