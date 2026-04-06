-- Sprint 1: Three-table conversation model
-- conversations + conversation_participants + restructured messages

-- New table: conversations
CREATE TABLE IF NOT EXISTS conversations (
    id              UUID PRIMARY KEY,
    type            VARCHAR(20) NOT NULL DEFAULT 'direct',
    project         VARCHAR(128),
    name            VARCHAR(256),
    created_by      VARCHAR(64) NOT NULL REFERENCES users(id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conv_type_project ON conversations(type, project);

-- Unique project group per project
CREATE UNIQUE INDEX IF NOT EXISTS idx_conv_project_group
    ON conversations(project) WHERE type = 'project_group';

-- New table: conversation_participants
CREATE TABLE IF NOT EXISTS conversation_participants (
    conversation_id     UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id             VARCHAR(64) NOT NULL REFERENCES users(id),
    joined_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    last_read_sequence  BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (conversation_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_cp_user ON conversation_participants(user_id);

-- Add new columns to messages
ALTER TABLE messages ADD COLUMN IF NOT EXISTS conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS sequence_number BIGINT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS content_type VARCHAR(64) NOT NULL DEFAULT 'text/plain';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(256);
