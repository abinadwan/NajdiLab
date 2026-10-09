CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_source_turn_role
ON messages(conversation_id, source_message_id, role)
WHERE source_message_id IS NOT NULL;

