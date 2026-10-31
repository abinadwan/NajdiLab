-- Additive only. A new table, not ALTER TABLE, so a replay after the loader's
-- schema-commit/ledger-insert crash gap stays idempotent, as in migration 005.
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS chat_session_bindings (
    session_id TEXT PRIMARY KEY REFERENCES chat_sessions(id),
    load_approved INTEGER NOT NULL DEFAULT 0 CHECK(load_approved IN (0,1)),
    model_fingerprint TEXT
);
COMMIT;
