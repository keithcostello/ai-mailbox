-- Sprint 8: Broadcast queue for AI-to-AI routing.
-- Requests are posted to a shared pool, not sent to specific users.
-- Matching AIs claim requests with two-gate human approval.

CREATE TABLE IF NOT EXISTS broadcast_requests (
    id UUID PRIMARY KEY,
    from_user VARCHAR(64) NOT NULL REFERENCES users(id),
    question TEXT NOT NULL,
    source_context TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    project VARCHAR(128) DEFAULT 'general',
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    conversation_id UUID REFERENCES conversations(id),
    response_message_id UUID REFERENCES messages(id),
    expires_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_broadcast_status ON broadcast_requests(status);
CREATE INDEX IF NOT EXISTS idx_broadcast_from ON broadcast_requests(from_user);
