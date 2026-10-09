PRAGMA foreign_keys = ON;

DROP INDEX IF EXISTS idx_training_attempts_job;
DROP INDEX IF EXISTS idx_training_jobs_status;
DROP TABLE IF EXISTS training_attempts;
DROP TABLE IF EXISTS training_jobs;
DROP TABLE IF EXISTS model_registry;
