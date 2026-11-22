-- Chat Experience V2. Lossless rebuild: SQLite cannot change the provider CHECK
-- in place, and NajdiLab Native needs provider 'native'. Every existing row,
-- id and value is copied and counted before the old table is dropped. Existing
-- conversations keep status/revision; new metadata starts empty (NULL), so no
-- title, pin or archive state is invented. Rollback: docs/development/CHAT_EXPERIENCE_V2.md.
PRAGMA foreign_keys = OFF;
BEGIN IMMEDIATE;

CREATE TEMP TABLE _migration_008_counts (
    session_count INTEGER NOT NULL,
    archived_count INTEGER NOT NULL,
    revision_sum INTEGER NOT NULL,
    request_count INTEGER NOT NULL,
    turn_count INTEGER NOT NULL,
    binding_count INTEGER NOT NULL
);

INSERT INTO _migration_008_counts
SELECT
    (SELECT COUNT(*) FROM chat_sessions),
    (SELECT COUNT(*) FROM chat_sessions WHERE status = 'ARCHIVED'),
    (SELECT COALESCE(SUM(revision), 0) FROM chat_sessions),
    (SELECT COUNT(*) FROM chat_requests),
    (SELECT COUNT(*) FROM chat_turns),
    (SELECT COUNT(*) FROM chat_session_bindings);

-- The trigger names chat_sessions; drop it across the rebuild and recreate it
-- unchanged so the rename never sees a dangling reference.
DROP TRIGGER IF EXISTS chat_archive_eligibility;

CREATE TABLE chat_sessions_new (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL CHECK(provider IN ('lmstudio','ollama','native')),
    model TEXT NOT NULL,
    context_budget INTEGER NOT NULL CHECK(context_budget BETWEEN 128 AND 1048576),
    reply_reserve INTEGER NOT NULL CHECK(reply_reserve > 0 AND reply_reserve < context_budget),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','CONTEXT_LIMIT','ARCHIVED')),
    revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    title TEXT CHECK(title IS NULL OR length(title) BETWEEN 1 AND 120),
    title_source TEXT CHECK(title_source IS NULL OR title_source IN ('auto','manual')),
    pinned_at TEXT,
    archived_at TEXT,
    archived_from_status TEXT CHECK(archived_from_status IS NULL OR archived_from_status IN ('OPEN','CONTEXT_LIMIT')),
    last_activity_at TEXT,
    CHECK((title IS NULL) = (title_source IS NULL)),
    CHECK(status = 'ARCHIVED' OR (archived_at IS NULL AND archived_from_status IS NULL))
);

-- Legacy archived rows have no recorded pre-archive status (NULL); restoring
-- them reopens as OPEN, and every send-time gate still applies. Columns stay
-- nullable so a pre-V2 style INSERT keeps working (lists use COALESCE).
INSERT INTO chat_sessions_new(id, provider, model, context_budget, reply_reserve, status, revision,
    created_at, updated_at, title, title_source, pinned_at, archived_at, archived_from_status, last_activity_at)
SELECT id, provider, model, context_budget, reply_reserve, status, revision,
    created_at, updated_at, NULL, NULL, NULL,
    CASE WHEN status = 'ARCHIVED' THEN updated_at END, NULL, updated_at
FROM chat_sessions;

CREATE TEMP TABLE _migration_008_assert (ok INTEGER NOT NULL CHECK (ok = 1));
INSERT INTO _migration_008_assert(ok)
SELECT CASE WHEN
    (SELECT COUNT(*) FROM chat_sessions_new) = (SELECT session_count FROM _migration_008_counts)
    AND (SELECT COUNT(*) FROM chat_sessions_new WHERE status = 'ARCHIVED') = (SELECT archived_count FROM _migration_008_counts)
    AND (SELECT COALESCE(SUM(revision), 0) FROM chat_sessions_new) = (SELECT revision_sum FROM _migration_008_counts)
    AND NOT EXISTS (SELECT 1 FROM chat_sessions o LEFT JOIN chat_sessions_new n ON n.id = o.id
                    WHERE n.id IS NULL OR n.provider != o.provider OR n.model != o.model
                       OR n.context_budget != o.context_budget OR n.reply_reserve != o.reply_reserve
                       OR n.status != o.status OR n.created_at != o.created_at OR n.updated_at != o.updated_at)
THEN 1 ELSE 0 END;

DROP TABLE chat_sessions;
ALTER TABLE chat_sessions_new RENAME TO chat_sessions;

CREATE INDEX idx_chat_sessions_activity ON chat_sessions(status, pinned_at, last_activity_at);

CREATE TRIGGER chat_archive_eligibility BEFORE UPDATE OF training_eligible ON reviews
WHEN NEW.training_eligible=1 AND EXISTS (
    SELECT 1 FROM messages m JOIN chat_turns t ON t.review_conversation_id=m.conversation_id
    JOIN chat_sessions s ON s.id=t.session_id
    WHERE m.id=NEW.message_id AND s.status='ARCHIVED'
)
BEGIN SELECT RAISE(ABORT, 'Archived chat cannot become training eligible'); END;

-- Content-free evidence that a permanent deletion happened. No text, title,
-- model output or hash of content is stored here.
CREATE TABLE chat_deletions (
    session_id TEXT PRIMARY KEY,
    deleted_at TEXT NOT NULL,
    policy TEXT NOT NULL,
    turns_deleted INTEGER NOT NULL CHECK (turns_deleted >= 0),
    requests_deleted INTEGER NOT NULL CHECK (requests_deleted >= 0),
    review_conversations_deleted INTEGER NOT NULL CHECK (review_conversations_deleted >= 0),
    review_conversations_redacted INTEGER NOT NULL CHECK (review_conversations_redacted >= 0),
    review_events_retained INTEGER NOT NULL CHECK (review_events_retained >= 0)
);

CREATE TRIGGER chat_deletions_immutable_update BEFORE UPDATE ON chat_deletions
BEGIN SELECT RAISE(ABORT, 'chat_deletions are immutable'); END;
CREATE TRIGGER chat_deletions_immutable_delete BEFORE DELETE ON chat_deletions
BEGIN SELECT RAISE(ABORT, 'chat_deletions are immutable'); END;

INSERT INTO _migration_008_assert(ok)
SELECT CASE WHEN
    (SELECT COUNT(*) FROM chat_requests) = (SELECT request_count FROM _migration_008_counts)
    AND (SELECT COUNT(*) FROM chat_turns) = (SELECT turn_count FROM _migration_008_counts)
    AND (SELECT COUNT(*) FROM chat_session_bindings) = (SELECT binding_count FROM _migration_008_counts)
    AND NOT EXISTS (SELECT 1 FROM chat_requests r LEFT JOIN chat_sessions s ON s.id = r.session_id WHERE s.id IS NULL)
    AND NOT EXISTS (SELECT 1 FROM chat_session_bindings b LEFT JOIN chat_sessions s ON s.id = b.session_id WHERE s.id IS NULL)
THEN 1 ELSE 0 END;

DROP TABLE _migration_008_assert;
DROP TABLE _migration_008_counts;
COMMIT;
PRAGMA foreign_keys = ON;
