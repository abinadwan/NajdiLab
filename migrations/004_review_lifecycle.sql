PRAGMA foreign_keys = OFF;
BEGIN IMMEDIATE;

-- SQLite cannot alter the CHECK constraint on reviews.review_status in place.
-- Rebuild the table while preserving every existing id and value, then assert
-- that the copy is lossless before the old table is dropped.
CREATE TEMP TABLE _migration_004_counts (
    review_count INTEGER NOT NULL,
    review_id_sum INTEGER NOT NULL,
    message_id_sum INTEGER NOT NULL,
    tag_count INTEGER NOT NULL
);

INSERT INTO _migration_004_counts(review_count, review_id_sum, message_id_sum, tag_count)
SELECT
    (SELECT COUNT(*) FROM reviews),
    (SELECT COALESCE(SUM(id), 0) FROM reviews),
    (SELECT COALESCE(SUM(message_id), 0) FROM reviews),
    (SELECT COUNT(*) FROM review_tags);

CREATE TABLE reviews_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL UNIQUE REFERENCES messages(id) ON DELETE CASCADE,
    review_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
        review_status IN (
            'PENDING', 'FULL_CORRECTION', 'DIALECT_CORRECTION',
            'CONTENT_CORRECTION', 'APPROVED', 'IGNORED', 'DELETED'
        )
    ),
    original_response TEXT NOT NULL,
    corrected_response TEXT,
    review_notes TEXT,
    reviewer TEXT NOT NULL DEFAULT 'human' CHECK (reviewer IN ('human', 'ai_suggestion', 'import')),
    training_eligible INTEGER NOT NULL DEFAULT 0 CHECK (training_eligible IN (0, 1)),
    exclude_from_training INTEGER NOT NULL DEFAULT 0 CHECK (exclude_from_training IN (0, 1)),
    evaluation_only INTEGER NOT NULL DEFAULT 0 CHECK (evaluation_only IN (0, 1)),
    contains_sensitive_data INTEGER NOT NULL DEFAULT 0 CHECK (contains_sensitive_data IN (0, 1)),
    contains_personal_data INTEGER NOT NULL DEFAULT 0 CHECK (contains_personal_data IN (0, 1)),
    needs_fact_check INTEGER NOT NULL DEFAULT 0 CHECK (needs_fact_check IN (0, 1)),
    ignored_at TEXT,
    ignored_reason TEXT,
    deleted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (review_status = 'APPROVED' AND corrected_response IS NULL)
        OR review_status IN ('PENDING', 'IGNORED', 'DELETED')
        OR (
            review_status IN ('FULL_CORRECTION', 'DIALECT_CORRECTION', 'CONTENT_CORRECTION')
            AND corrected_response IS NOT NULL
        )
    ),
    CHECK (review_status NOT IN ('IGNORED', 'DELETED') OR training_eligible = 0),
    CHECK (review_status != 'IGNORED' OR ignored_at IS NOT NULL),
    CHECK (review_status != 'DELETED' OR deleted_at IS NOT NULL)
);

INSERT INTO reviews_new(
    id, message_id, review_status, original_response, corrected_response,
    review_notes, reviewer, training_eligible, exclude_from_training,
    evaluation_only, contains_sensitive_data, contains_personal_data,
    needs_fact_check, ignored_at, ignored_reason, deleted_at, created_at, updated_at
)
SELECT
    id, message_id, review_status, original_response, corrected_response,
    review_notes, reviewer, training_eligible, exclude_from_training,
    evaluation_only, contains_sensitive_data, contains_personal_data,
    needs_fact_check, NULL, NULL, NULL, created_at, updated_at
FROM reviews;

CREATE TEMP TABLE _migration_004_assert (
    ok INTEGER NOT NULL CHECK (ok = 1)
);

INSERT INTO _migration_004_assert(ok)
SELECT CASE WHEN
    (SELECT COUNT(*) FROM reviews_new) = (SELECT review_count FROM _migration_004_counts)
    AND (SELECT COALESCE(SUM(id), 0) FROM reviews_new) = (SELECT review_id_sum FROM _migration_004_counts)
    AND (SELECT COALESCE(SUM(message_id), 0) FROM reviews_new) = (SELECT message_id_sum FROM _migration_004_counts)
    AND (SELECT COUNT(*) FROM review_tags) = (SELECT tag_count FROM _migration_004_counts)
THEN 1 ELSE 0 END;

DROP TABLE reviews;
ALTER TABLE reviews_new RENAME TO reviews;

CREATE INDEX idx_reviews_status ON reviews(review_status);
CREATE INDEX idx_reviews_training ON reviews(training_eligible, evaluation_only, exclude_from_training);
CREATE INDEX idx_reviews_lifecycle ON reviews(review_status, ignored_at, deleted_at, updated_at);

-- Manual items already have training/archival gates.  Add only lifecycle audit
-- timestamps/reason fields; no redundant review_status column is introduced.
ALTER TABLE manual_sft_items ADD COLUMN ignored_at TEXT;
ALTER TABLE manual_sft_items ADD COLUMN ignored_reason TEXT;
ALTER TABLE manual_sft_items ADD COLUMN deleted_at TEXT;

ALTER TABLE direct_language_texts ADD COLUMN ignored_at TEXT;
ALTER TABLE direct_language_texts ADD COLUMN ignored_reason TEXT;
ALTER TABLE direct_language_texts ADD COLUMN deleted_at TEXT;

ALTER TABLE preference_pairs ADD COLUMN ignored_at TEXT;
ALTER TABLE preference_pairs ADD COLUMN ignored_reason TEXT;
ALTER TABLE preference_pairs ADD COLUMN deleted_at TEXT;

CREATE INDEX idx_manual_sft_lifecycle
    ON manual_sft_items(deleted_at, ignored_at, archived, exclude_from_training, training_eligible);
CREATE INDEX idx_direct_lifecycle
    ON direct_language_texts(deleted_at, ignored_at, archived, exclude_from_training, training_eligible);
CREATE INDEX idx_preference_lifecycle
    ON preference_pairs(deleted_at, ignored_at, archived, exclude_from_training, training_eligible);

DROP TABLE _migration_004_assert;
DROP TABLE _migration_004_counts;

COMMIT;
PRAGMA foreign_keys = ON;
