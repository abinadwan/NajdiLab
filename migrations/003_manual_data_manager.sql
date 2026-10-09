PRAGMA foreign_keys = ON;

ALTER TABLE manual_sft_items ADD COLUMN source TEXT NOT NULL DEFAULT 'NajdiLab manual entry';
ALTER TABLE manual_sft_items ADD COLUMN source_type TEXT NOT NULL DEFAULT 'human_written';
ALTER TABLE manual_sft_items ADD COLUMN version_number INTEGER NOT NULL DEFAULT 1 CHECK (version_number >= 1);
ALTER TABLE manual_sft_items ADD COLUMN archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1));
ALTER TABLE manual_sft_items ADD COLUMN parent_item_id INTEGER REFERENCES manual_sft_items(id) ON DELETE SET NULL;
ALTER TABLE manual_sft_items ADD COLUMN updated_at TEXT;
UPDATE manual_sft_items SET updated_at = created_at WHERE updated_at IS NULL;
UPDATE manual_sft_items SET source_type = 'synthetic_reviewed' WHERE origin = 'synthetic_reviewed';

ALTER TABLE preference_pairs ADD COLUMN source TEXT NOT NULL DEFAULT 'NajdiLab manual entry';
ALTER TABLE preference_pairs ADD COLUMN source_type TEXT NOT NULL DEFAULT 'human_written';
ALTER TABLE preference_pairs ADD COLUMN version_number INTEGER NOT NULL DEFAULT 1 CHECK (version_number >= 1);
ALTER TABLE preference_pairs ADD COLUMN archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1));
ALTER TABLE preference_pairs ADD COLUMN parent_item_id INTEGER REFERENCES preference_pairs(id) ON DELETE SET NULL;
ALTER TABLE preference_pairs ADD COLUMN updated_at TEXT;
UPDATE preference_pairs SET updated_at = created_at WHERE updated_at IS NULL;
UPDATE preference_pairs SET source_type = 'synthetic_reviewed' WHERE origin = 'synthetic_reviewed';

-- Rebuild only this table to extend the existing language-layer CHECK safely.
-- The copy is lossless and remains inside the migration transaction managed by SQLite.
ALTER TABLE direct_language_texts RENAME TO direct_language_texts_legacy_003;

CREATE TABLE direct_language_texts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    language_layer TEXT NOT NULL CHECK (language_layer IN ('najdi_riyadh', 'saudi_neutral', 'msa', 'technical_arabic', 'formal_arabic')),
    domain TEXT,
    source TEXT,
    source_type TEXT NOT NULL CHECK (source_type IN ('human_written', 'human_corrected', 'synthetic_reviewed', 'external_licensed')),
    origin TEXT NOT NULL,
    notes TEXT,
    training_eligible INTEGER NOT NULL DEFAULT 0 CHECK (training_eligible IN (0, 1)),
    exclude_from_training INTEGER NOT NULL DEFAULT 0 CHECK (exclude_from_training IN (0, 1)),
    evaluation_only INTEGER NOT NULL DEFAULT 0 CHECK (evaluation_only IN (0, 1)),
    contains_sensitive_data INTEGER NOT NULL DEFAULT 0 CHECK (contains_sensitive_data IN (0, 1)),
    contains_personal_data INTEGER NOT NULL DEFAULT 0 CHECK (contains_personal_data IN (0, 1)),
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    demo INTEGER NOT NULL DEFAULT 0 CHECK (demo IN (0, 1)),
    version_number INTEGER NOT NULL DEFAULT 1 CHECK (version_number >= 1),
    archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
    parent_item_id INTEGER REFERENCES direct_language_texts(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO direct_language_texts(
    id, text, language_layer, domain, source, source_type, origin, notes,
    training_eligible, exclude_from_training, evaluation_only,
    contains_sensitive_data, contains_personal_data, created_at, metadata_json,
    demo, version_number, archived, parent_item_id, updated_at
)
SELECT
    id, text, language_layer, domain, source, source_type, origin, notes,
    training_eligible, exclude_from_training, evaluation_only,
    contains_sensitive_data, contains_personal_data, created_at, metadata_json,
    demo, 1, 0, NULL, created_at
FROM direct_language_texts_legacy_003;

DROP TABLE direct_language_texts_legacy_003;

CREATE TABLE manual_data_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type TEXT NOT NULL CHECK (item_type IN ('sft', 'direct', 'dpo')),
    item_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL CHECK (version_number >= 1),
    snapshot_json TEXT NOT NULL,
    changed_fields_json TEXT NOT NULL DEFAULT '[]',
    change_notes TEXT,
    changed_by TEXT NOT NULL DEFAULT 'human' CHECK (changed_by IN ('human', 'system')),
    created_at TEXT NOT NULL,
    UNIQUE(item_type, item_id, version_number)
);

CREATE TABLE manual_data_export_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type TEXT NOT NULL CHECK (item_type IN ('sft', 'direct', 'dpo')),
    item_id INTEGER NOT NULL,
    dataset_version_id INTEGER NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    exported_at TEXT NOT NULL,
    UNIQUE(item_type, item_id, dataset_version_id)
);

CREATE INDEX idx_manual_sft_manager ON manual_sft_items(archived, exclude_from_training, training_eligible, updated_at);
CREATE INDEX idx_direct_manager ON direct_language_texts(archived, exclude_from_training, training_eligible, updated_at);
CREATE INDEX idx_preference_manager ON preference_pairs(archived, exclude_from_training, training_eligible, updated_at);
CREATE INDEX idx_manual_versions_item ON manual_data_versions(item_type, item_id, version_number DESC);
CREATE INDEX idx_manual_export_history_item ON manual_data_export_history(item_type, item_id);
