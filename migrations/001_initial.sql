PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_conversation_id TEXT NOT NULL UNIQUE,
    title TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    channel TEXT NOT NULL DEFAULT 'manual',
    provider TEXT,
    model_name TEXT,
    model_version TEXT,
    system_prompt_version TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    demo INTEGER NOT NULL DEFAULT 0 CHECK (demo IN (0, 1))
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    turn_index INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
    content TEXT NOT NULL,
    provider TEXT,
    model_name TEXT,
    model_version TEXT,
    created_at TEXT NOT NULL,
    generation_settings_json TEXT NOT NULL DEFAULT '{}',
    token_usage_json TEXT NOT NULL DEFAULT '{}',
    latency_ms INTEGER,
    source_message_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    parent_message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
    candidate_group_id TEXT,
    judge_result_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(conversation_id, turn_index)
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL UNIQUE REFERENCES messages(id) ON DELETE CASCADE,
    review_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
        review_status IN ('PENDING', 'FULL_CORRECTION', 'DIALECT_CORRECTION', 'CONTENT_CORRECTION', 'APPROVED')
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
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (review_status = 'APPROVED' AND corrected_response IS NULL)
        OR review_status = 'PENDING'
        OR (review_status IN ('FULL_CORRECTION', 'DIALECT_CORRECTION', 'CONTENT_CORRECTION') AND corrected_response IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS review_tags (
    review_id INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    tag TEXT NOT NULL CHECK (tag IN (
        'forgot_previous_constraint', 'ignored_user_instruction', 'wrong_context',
        'repeated_rejected_option', 'contradiction', 'hallucination', 'dialect_issue',
        'grammar_issue', 'unnatural_arabic', 'too_verbose', 'too_short',
        'format_failure', 'factual_error', 'other'
    )),
    PRIMARY KEY (review_id, tag)
);

CREATE TABLE IF NOT EXISTS manual_sft_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    messages_json TEXT NOT NULL,
    language_layer TEXT NOT NULL,
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
    demo INTEGER NOT NULL DEFAULT 0 CHECK (demo IN (0, 1))
);

CREATE TABLE IF NOT EXISTS direct_language_texts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    language_layer TEXT NOT NULL CHECK (language_layer IN ('najdi_riyadh', 'saudi_neutral', 'msa')),
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
    demo INTEGER NOT NULL DEFAULT 0 CHECK (demo IN (0, 1))
);

CREATE TABLE IF NOT EXISTS preference_pairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_context_json TEXT NOT NULL,
    rejected_response TEXT NOT NULL,
    preferred_response TEXT NOT NULL,
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
    demo INTEGER NOT NULL DEFAULT 0 CHECK (demo IN (0, 1))
);

CREATE TABLE IF NOT EXISTS comparison_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
    context_json TEXT NOT NULL,
    candidate_group_id TEXT NOT NULL,
    model_a_message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
    model_b_message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
    judge_result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dataset_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    manifest_json TEXT NOT NULL,
    export_path TEXT NOT NULL,
    filters_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_turn ON messages(conversation_id, turn_index);
CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);
CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(review_status);
CREATE INDEX IF NOT EXISTS idx_reviews_training ON reviews(training_eligible, evaluation_only, exclude_from_training);
CREATE INDEX IF NOT EXISTS idx_conversations_source_model ON conversations(source, model_name);
CREATE INDEX IF NOT EXISTS idx_conversations_channel ON conversations(channel);
CREATE INDEX IF NOT EXISTS idx_review_tags_tag ON review_tags(tag);

