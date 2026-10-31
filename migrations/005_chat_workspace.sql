-- Additive only. Existing conversations, reviews, exports and migrations remain.
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL CHECK(provider IN ('lmstudio','ollama')),
    model TEXT NOT NULL,
    context_budget INTEGER NOT NULL CHECK(context_budget BETWEEN 128 AND 1048576),
    reply_reserve INTEGER NOT NULL CHECK(reply_reserve > 0 AND reply_reserve < context_budget),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','CONTEXT_LIMIT','ARCHIVED')),
    revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_requests (
    session_id TEXT NOT NULL REFERENCES chat_sessions(id),
    request_id TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('RUNNING','COMPLETED','FAILED','STOPPED','INTERRUPTED','CONTEXT_LIMIT')),
    created_at TEXT NOT NULL,
    PRIMARY KEY(session_id,request_id)
);
CREATE TABLE IF NOT EXISTS chat_turns (
    session_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    user_content TEXT NOT NULL,
    assistant_content TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    review_conversation_id INTEGER REFERENCES conversations(id),
    created_at TEXT NOT NULL,
    PRIMARY KEY(session_id,request_id),
    UNIQUE(session_id,ordinal),
    FOREIGN KEY(session_id,request_id) REFERENCES chat_requests(session_id,request_id)
);
CREATE TRIGGER IF NOT EXISTS chat_archive_eligibility BEFORE UPDATE OF training_eligible ON reviews
WHEN NEW.training_eligible=1 AND EXISTS (
    SELECT 1 FROM messages m JOIN chat_turns t ON t.review_conversation_id=m.conversation_id
    JOIN chat_sessions s ON s.id=t.session_id
    WHERE m.id=NEW.message_id AND s.status='ARCHIVED'
)
BEGIN SELECT RAISE(ABORT, 'Archived chat cannot become training eligible'); END;
COMMIT;
