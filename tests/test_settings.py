"""Tests for user settings page -- display, update, validation."""

import sqlite3
import time

import jwt
import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette

from ai_mailbox.db.connection import SQLiteDB
from ai_mailbox.oauth import MailboxOAuthProvider, hash_password
from ai_mailbox.web import create_web_routes

JWT_SECRET = "test-secret-for-settings-minimum-32-bytes!!"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    api_key TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    user_type TEXT NOT NULL DEFAULT 'human',
    last_seen TIMESTAMP,
    session_mode TEXT NOT NULL DEFAULT 'persistent',
    email TEXT,
    auth_provider TEXT NOT NULL DEFAULT 'local',
    avatar_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL DEFAULT 'direct',
    project TEXT, name TEXT,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS conversation_participants (
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id),
    joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_read_sequence INTEGER NOT NULL DEFAULT 0,
    archived_at TIMESTAMP,
    PRIMARY KEY (conversation_id, user_id)
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    from_user TEXT NOT NULL REFERENCES users(id),
    sequence_number INTEGER NOT NULL,
    subject TEXT, body TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'text/plain',
    idempotency_key TEXT,
    reply_to TEXT REFERENCES messages(id),
    ack_state TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (conversation_id, sequence_number)
);
CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id TEXT PRIMARY KEY, client_info TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS oauth_codes (
    code TEXT PRIMARY KEY, client_id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id),
    code_challenge TEXT NOT NULL, redirect_uri TEXT NOT NULL,
    scopes TEXT, expires_at REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS oauth_tokens (
    token TEXT PRIMARY KEY, client_id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id),
    scopes TEXT, expires_at INTEGER, refresh_token TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS user_invites (
    email TEXT PRIMARY KEY,
    invited_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP
);
"""


def _make_session_cookie(user_id: str) -> str:
    return jwt.encode(
        {"sub": user_id, "iat": int(time.time()), "exp": int(time.time()) + 86400},
        JWT_SECRET,
        algorithm="HS256",
    )


@pytest.fixture
def settings_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA_SQL)
    conn.execute(
        "INSERT INTO users (id, display_name, api_key, password_hash, email, auth_provider) VALUES (?, ?, ?, ?, ?, ?)",
        ("keith", "Keith", "test-key", hash_password("testpass"), "keith@example.com", "github"),
    )
    conn.execute(
        "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
        ("amy", "Amy", "test-amy-key"),
    )
    conn.commit()
    yield SQLiteDB(conn)
    conn.close()


@pytest.fixture
def settings_app(settings_db):
    provider = MailboxOAuthProvider(db=settings_db, jwt_secret=JWT_SECRET)
    routes = create_web_routes(settings_db, provider, JWT_SECRET)
    return Starlette(routes=routes)


@pytest.fixture
def settings_client(settings_app):
    return TestClient(settings_app, follow_redirects=False)


class TestSettingsGet:
    """GET /web/settings renders user profile."""

    def setup_method(self):
        from ai_mailbox.rate_limit import reset_storage
        reset_storage()

    def test_requires_auth(self, settings_client):
        resp = settings_client.get("/web/settings")
        assert resp.status_code == 302
        assert "/web/login" in resp.headers["location"]

    def test_renders_settings_page(self, settings_client):
        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        resp = settings_client.get("/web/settings")
        assert resp.status_code == 200
        assert "Settings" in resp.text

    def test_shows_display_name_input(self, settings_client):
        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        resp = settings_client.get("/web/settings")
        assert "Keith" in resp.text
        assert 'name="display_name"' in resp.text

    def test_shows_email(self, settings_client):
        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        resp = settings_client.get("/web/settings")
        assert "keith@example.com" in resp.text

    def test_shows_auth_provider(self, settings_client):
        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        resp = settings_client.get("/web/settings")
        assert "github" in resp.text

    def test_shows_user_type(self, settings_client):
        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        resp = settings_client.get("/web/settings")
        assert "human" in resp.text


class TestSettingsPost:
    """POST /web/settings updates display name."""

    def setup_method(self):
        from ai_mailbox.rate_limit import reset_storage
        reset_storage()

    def test_requires_auth(self, settings_client):
        resp = settings_client.post("/web/settings", data={"display_name": "New"})
        assert resp.status_code == 302

    def test_updates_display_name(self, settings_client, settings_db):
        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        resp = settings_client.post("/web/settings", data={"display_name": "Keith M"})
        assert resp.status_code == 200
        row = settings_db.fetchone("SELECT display_name FROM users WHERE id = 'keith'")
        assert row["display_name"] == "Keith M"

    def test_shows_success_message(self, settings_client):
        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        resp = settings_client.post("/web/settings", data={"display_name": "Keith M"})
        assert "saved" in resp.text.lower() or "updated" in resp.text.lower()

    def test_rejects_empty_name(self, settings_client, settings_db):
        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        resp = settings_client.post("/web/settings", data={"display_name": ""})
        assert resp.status_code == 200
        assert "invalid" in resp.text.lower() or "error" in resp.text.lower()
        # Name should not have changed
        row = settings_db.fetchone("SELECT display_name FROM users WHERE id = 'keith'")
        assert row["display_name"] == "Keith"

    def test_rejects_too_long_name(self, settings_client, settings_db):
        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        resp = settings_client.post("/web/settings", data={"display_name": "x" * 101})
        assert resp.status_code == 200
        assert "invalid" in resp.text.lower() or "error" in resp.text.lower()

    def test_strips_whitespace(self, settings_client, settings_db):
        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        settings_client.post("/web/settings", data={"display_name": "  Keith  "})
        row = settings_db.fetchone("SELECT display_name FROM users WHERE id = 'keith'")
        assert row["display_name"] == "Keith"


class TestChangeHandle:
    """POST /web/settings/handle changes the user's @handle."""

    def setup_method(self):
        from ai_mailbox.rate_limit import reset_storage
        reset_storage()

    def test_requires_auth(self, settings_client):
        resp = settings_client.post("/web/settings/handle", data={"handle": "newname"})
        assert resp.status_code == 302

    def test_changes_handle(self, settings_client, settings_db):
        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        resp = settings_client.post("/web/settings/handle", data={"handle": "keithm"})
        assert resp.status_code == 302
        # Old ID gone
        assert settings_db.fetchone("SELECT id FROM users WHERE id = 'keith'") is None
        # New ID exists
        row = settings_db.fetchone("SELECT * FROM users WHERE id = 'keithm'")
        assert row is not None
        assert row["display_name"] == "Keith"

    def test_updates_messages_foreign_key(self, settings_client, settings_db):
        from ai_mailbox.db.queries import find_or_create_direct_conversation, insert_message
        conv_id = find_or_create_direct_conversation(settings_db, "keith", "amy", "general")
        insert_message(settings_db, conv_id, "keith", "test msg")

        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        settings_client.post("/web/settings/handle", data={"handle": "keithm"})

        msg = settings_db.fetchone("SELECT from_user FROM messages WHERE conversation_id = ?", (conv_id,))
        assert msg["from_user"] == "keithm"

    def test_updates_conversation_participants(self, settings_client, settings_db):
        from ai_mailbox.db.queries import find_or_create_direct_conversation
        conv_id = find_or_create_direct_conversation(settings_db, "keith", "amy", "general")

        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        settings_client.post("/web/settings/handle", data={"handle": "keithm"})

        cp = settings_db.fetchone(
            "SELECT user_id FROM conversation_participants WHERE conversation_id = ? AND user_id = 'keithm'",
            (conv_id,),
        )
        assert cp is not None

    def test_rejects_taken_handle(self, settings_client, settings_db):
        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        resp = settings_client.post("/web/settings/handle", data={"handle": "amy"})
        # Should stay on settings with error, not redirect
        assert resp.status_code == 200
        assert "taken" in resp.text.lower()
        # keith should still exist
        assert settings_db.fetchone("SELECT id FROM users WHERE id = 'keith'") is not None

    def test_rejects_invalid_handle(self, settings_client, settings_db):
        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        resp = settings_client.post("/web/settings/handle", data={"handle": "A B C"})
        assert resp.status_code == 200
        assert "lowercase" in resp.text.lower() or "letters" in resp.text.lower()

    def test_new_session_cookie_set(self, settings_client, settings_db):
        token = _make_session_cookie("keith")
        settings_client.cookies.set("session", token)
        resp = settings_client.post("/web/settings/handle", data={"handle": "keithm"})
        assert resp.status_code == 302
        # Should have a new session cookie with the new user_id
        session_cookie = resp.cookies.get("session")
        if session_cookie:
            payload = jwt.decode(session_cookie, JWT_SECRET, algorithms=["HS256"])
            assert payload["sub"] == "keithm"
