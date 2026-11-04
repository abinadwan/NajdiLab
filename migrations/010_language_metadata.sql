PRAGMA foreign_keys = OFF;

BEGIN IMMEDIATE;

-- V2.2.0 language metadata: language, dialect and style beside the existing domain.
-- The legacy language_layer value is kept on every record. It becomes optional, so text that
-- is not Arabic no longer needs an Arabic layer. SQLite cannot relax NOT NULL or CHECK in
-- place, so the two tables that declare them are rebuilt with an explicit, lossless column
-- copy (ids kept). Their AUTOINCREMENT counters are carried over, so the id of a deleted
-- record is never reused and record history stays unambiguous.

ALTER TABLE manual_sft_items RENAME TO manual_sft_items_legacy_010;

CREATE TABLE manual_sft_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    messages_json TEXT NOT NULL,
    language_layer TEXT,
    domain TEXT,
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
    source TEXT NOT NULL DEFAULT 'NajdiLab manual entry',
    source_type TEXT NOT NULL DEFAULT 'human_written',
    version_number INTEGER NOT NULL DEFAULT 1 CHECK (version_number >= 1),
    archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
    parent_item_id INTEGER REFERENCES manual_sft_items(id) ON DELETE SET NULL,
    updated_at TEXT,
    ignored_at TEXT,
    ignored_reason TEXT,
    deleted_at TEXT,
    language TEXT,
    dialect TEXT,
    style TEXT
);

INSERT INTO manual_sft_items(
    id, messages_json, language_layer, domain, origin, notes, training_eligible, exclude_from_training,
    evaluation_only, contains_sensitive_data, contains_personal_data, created_at, metadata_json, demo,
    source, source_type, version_number, archived, parent_item_id, updated_at, ignored_at, ignored_reason, deleted_at
)
SELECT
    id, messages_json, language_layer, domain, origin, notes, training_eligible, exclude_from_training,
    evaluation_only, contains_sensitive_data, contains_personal_data, created_at, metadata_json, demo,
    source, source_type, version_number, archived, parent_item_id, updated_at, ignored_at, ignored_reason, deleted_at
FROM manual_sft_items_legacy_010;

UPDATE sqlite_sequence
SET seq = (SELECT MAX(seq) FROM sqlite_sequence WHERE name IN ('manual_sft_items', 'manual_sft_items_legacy_010'))
WHERE name = 'manual_sft_items';

INSERT INTO sqlite_sequence(name, seq)
SELECT 'manual_sft_items', seq FROM sqlite_sequence
WHERE name = 'manual_sft_items_legacy_010'
  AND NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'manual_sft_items');

DROP TABLE manual_sft_items_legacy_010;

CREATE INDEX idx_manual_sft_manager ON manual_sft_items(archived, exclude_from_training, training_eligible, updated_at);
CREATE INDEX idx_manual_sft_lifecycle
    ON manual_sft_items(deleted_at, ignored_at, archived, exclude_from_training, training_eligible);

ALTER TABLE direct_language_texts RENAME TO direct_language_texts_legacy_010;

CREATE TABLE direct_language_texts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    language_layer TEXT CHECK (language_layer IS NULL OR language_layer IN ('najdi_riyadh', 'saudi_neutral', 'msa', 'technical_arabic', 'formal_arabic')),
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
    updated_at TEXT NOT NULL,
    ignored_at TEXT,
    ignored_reason TEXT,
    deleted_at TEXT,
    language TEXT,
    dialect TEXT,
    style TEXT
);

INSERT INTO direct_language_texts(
    id, text, language_layer, domain, source, source_type, origin, notes, training_eligible, exclude_from_training,
    evaluation_only, contains_sensitive_data, contains_personal_data, created_at, metadata_json, demo,
    version_number, archived, parent_item_id, updated_at, ignored_at, ignored_reason, deleted_at
)
SELECT
    id, text, language_layer, domain, source, source_type, origin, notes, training_eligible, exclude_from_training,
    evaluation_only, contains_sensitive_data, contains_personal_data, created_at, metadata_json, demo,
    version_number, archived, parent_item_id, updated_at, ignored_at, ignored_reason, deleted_at
FROM direct_language_texts_legacy_010;

UPDATE sqlite_sequence
SET seq = (SELECT MAX(seq) FROM sqlite_sequence WHERE name IN ('direct_language_texts', 'direct_language_texts_legacy_010'))
WHERE name = 'direct_language_texts';

INSERT INTO sqlite_sequence(name, seq)
SELECT 'direct_language_texts', seq FROM sqlite_sequence
WHERE name = 'direct_language_texts_legacy_010'
  AND NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'direct_language_texts');

DROP TABLE direct_language_texts_legacy_010;

CREATE INDEX idx_direct_manager ON direct_language_texts(archived, exclude_from_training, training_eligible, updated_at);
CREATE INDEX idx_direct_lifecycle
    ON direct_language_texts(deleted_at, ignored_at, archived, exclude_from_training, training_eligible);

ALTER TABLE preference_pairs ADD COLUMN language TEXT;
ALTER TABLE preference_pairs ADD COLUMN dialect TEXT;
ALTER TABLE preference_pairs ADD COLUMN style TEXT;

-- Fill the new fields only where a legacy layer has a certain meaning (see app/language_taxonomy.py).
UPDATE manual_sft_items SET language = 'ar',
    dialect = CASE language_layer WHEN 'najdi_riyadh' THEN 'najdi_riyadh' WHEN 'saudi_neutral' THEN 'saudi_neutral' WHEN 'msa' THEN 'msa' END,
    style = CASE language_layer WHEN 'technical_arabic' THEN 'technical' WHEN 'formal_arabic' THEN 'formal' END
WHERE language_layer IN ('najdi_riyadh', 'saudi_neutral', 'msa', 'technical_arabic', 'formal_arabic');

UPDATE direct_language_texts SET language = 'ar',
    dialect = CASE language_layer WHEN 'najdi_riyadh' THEN 'najdi_riyadh' WHEN 'saudi_neutral' THEN 'saudi_neutral' WHEN 'msa' THEN 'msa' END,
    style = CASE language_layer WHEN 'technical_arabic' THEN 'technical' WHEN 'formal_arabic' THEN 'formal' END
WHERE language_layer IN ('najdi_riyadh', 'saudi_neutral', 'msa', 'technical_arabic', 'formal_arabic');

UPDATE preference_pairs SET language = 'ar',
    dialect = CASE language_layer WHEN 'najdi_riyadh' THEN 'najdi_riyadh' WHEN 'saudi_neutral' THEN 'saudi_neutral' WHEN 'msa' THEN 'msa' END,
    style = CASE language_layer WHEN 'technical_arabic' THEN 'technical' WHEN 'formal_arabic' THEN 'formal' END
WHERE language_layer IN ('najdi_riyadh', 'saudi_neutral', 'msa', 'technical_arabic', 'formal_arabic');

COMMIT;

PRAGMA foreign_keys = ON;
