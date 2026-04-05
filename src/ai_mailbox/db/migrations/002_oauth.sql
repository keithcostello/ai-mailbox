-- OAuth 2.1 support tables

ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(256);

CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id VARCHAR(128) PRIMARY KEY,
    client_info TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS oauth_codes (
    code VARCHAR(256) PRIMARY KEY,
    client_id VARCHAR(128) NOT NULL,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id),
    code_challenge VARCHAR(256) NOT NULL,
    redirect_uri TEXT NOT NULL,
    scopes TEXT,
    expires_at FLOAT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    token VARCHAR(256) PRIMARY KEY,
    client_id VARCHAR(128) NOT NULL,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id),
    scopes TEXT,
    expires_at INTEGER,
    refresh_token VARCHAR(256),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_oauth_tokens_refresh ON oauth_tokens(refresh_token);
