-- Sprint 6: OAuth registration, invite-only mode

-- OAuth identity fields on users
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(20) DEFAULT 'local';
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;

-- Invite-only registration
CREATE TABLE IF NOT EXISTS user_invites (
    email VARCHAR(255) PRIMARY KEY,
    invited_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP
);

-- Index for OAuth user lookup
CREATE INDEX IF NOT EXISTS idx_users_email_provider ON users(email, auth_provider);
