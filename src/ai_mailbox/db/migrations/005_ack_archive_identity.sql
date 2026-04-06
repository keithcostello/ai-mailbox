-- Sprint 5: Acknowledgment, archiving, agent identity, tech debt fixes

-- Acknowledgment state on messages
ALTER TABLE messages ADD COLUMN IF NOT EXISTS ack_state VARCHAR(20) DEFAULT 'pending';

-- Per-user conversation archiving
ALTER TABLE conversation_participants ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP;

-- Agent identity fields on users
ALTER TABLE users ADD COLUMN IF NOT EXISTS user_type VARCHAR(20) DEFAULT 'human';
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS session_mode VARCHAR(20) DEFAULT 'persistent';
