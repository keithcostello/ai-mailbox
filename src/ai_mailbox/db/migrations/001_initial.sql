-- AI Mailbox schema: users + messages

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(64) PRIMARY KEY,
    display_name VARCHAR(128) NOT NULL,
    api_key VARCHAR(128) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_user VARCHAR(64) NOT NULL REFERENCES users(id),
    to_user VARCHAR(64) NOT NULL REFERENCES users(id),
    project VARCHAR(128) NOT NULL DEFAULT 'general',
    subject VARCHAR(256) DEFAULT NULL,
    body TEXT NOT NULL,
    reply_to UUID REFERENCES messages(id),
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_msg_inbox ON messages(to_user, project, read, created_at);
CREATE INDEX IF NOT EXISTS idx_msg_thread ON messages(reply_to);
