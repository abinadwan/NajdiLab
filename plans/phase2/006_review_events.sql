PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS review_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER NOT NULL REFERENCES reviews(id) ON DELETE RESTRICT,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT,
    correction_type TEXT,
    error_tags_json TEXT NOT NULL DEFAULT '[]',
    source_sha256 TEXT NOT NULL,
    correction_sha256 TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (review_id, sequence),
    CHECK (json_valid(error_tags_json)),
    CHECK (length(source_sha256) = 64),
    CHECK (correction_sha256 IS NULL OR length(correction_sha256) = 64)
);

CREATE INDEX IF NOT EXISTS idx_review_events_review_time
ON review_events(review_id, sequence, created_at);

CREATE TRIGGER IF NOT EXISTS review_events_immutable_update
BEFORE UPDATE ON review_events
BEGIN
    SELECT RAISE(ABORT, 'review_events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS review_events_immutable_delete
BEFORE DELETE ON review_events
BEGIN
    SELECT RAISE(ABORT, 'review_events are immutable');
END;

