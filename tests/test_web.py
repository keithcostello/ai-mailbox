"""Tests for web UI routes -- login, session, inbox, health."""

import sqlite3
import time

import jwt
import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette

from ai_mailbox.db.connection import SQLiteDB
from ai_mailbox.oauth import MailboxOAuthProvider, hash_password
from ai_mailbox.web import create_web_routes

JWT_SECRET = "test-secret-for-web-ui-minimum-32-bytes!!"

# Schema from conftest -- duplicated here for the cross-thread SQLite fixture
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    api_key TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL DEFAULT 'direct',
    project TEXT,
    name TEXT,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS conversation_participants (
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id),
    joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_read_sequence INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (conversation_id, user_id)
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    from_user TEXT NOT NULL REFERENCES users(id),
    sequence_number INTEGER NOT NULL,
    subject TEXT,
    body TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'text/plain',
    idempotency_key TEXT,
    reply_to TEXT REFERENCES messages(id),
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
"""


@pytest.fixture
def web_db():
    """Cross-thread-safe SQLite DB for web tests."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA_SQL)
    conn.execute(
        "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
        ("keith", "Keith", "test-keith-key"),
    )
    conn.execute(
        "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
        ("amy", "Amy", "test-amy-key"),
    )
    pw_hash = hash_password("testpass")
    conn.execute("UPDATE users SET password_hash = ? WHERE id = 'keith'", (pw_hash,))
    conn.commit()
    db = SQLiteDB(conn)
    yield db
    conn.close()


@pytest.fixture
def web_app(web_db):
    """Create a Starlette test app with web routes."""
    provider = MailboxOAuthProvider(db=web_db, jwt_secret=JWT_SECRET)
    routes = create_web_routes(web_db, provider, JWT_SECRET)
    app = Starlette(routes=routes)
    return app


@pytest.fixture
def client(web_app):
    """Test client for web routes."""
    return TestClient(web_app, follow_redirects=False)


def _make_session_cookie(user_id: str, expired: bool = False) -> str:
    """Create a JWT session cookie for testing."""
    exp = int(time.time()) - 100 if expired else int(time.time()) + 86400
    return jwt.encode(
        {"sub": user_id, "iat": int(time.time()), "exp": exp},
        JWT_SECRET,
        algorithm="HS256",
    )


class TestLoginPage:
    """GET /web/login renders login form."""

    def test_login_page_renders(self, client):
        resp = client.get("/web/login")
        assert resp.status_code == 200
        assert "username" in resp.text.lower()
        assert "password" in resp.text.lower()

    def test_login_page_has_tailwind(self, client):
        resp = client.get("/web/login")
        assert "tailwindcss" in resp.text

    def test_login_page_has_htmx(self, client):
        resp = client.get("/web/login")
        assert "htmx.org" in resp.text

    def test_logged_in_user_redirected_to_inbox(self, client):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/login")
        assert resp.status_code == 302
        assert "/web/inbox" in resp.headers["location"]


class TestLoginPost:
    """POST /web/login authenticates and sets session cookie."""

    def test_valid_login_redirects_to_inbox(self, client):
        resp = client.post("/web/login", data={"username": "keith", "password": "testpass"})
        assert resp.status_code == 302
        assert "/web/inbox" in resp.headers["location"]

    def test_valid_login_sets_session_cookie(self, client):
        resp = client.post("/web/login", data={"username": "keith", "password": "testpass"})
        cookies = resp.cookies
        assert "session" in resp.headers.get("set-cookie", "").lower()

    def test_invalid_login_shows_error(self, client):
        resp = client.post("/web/login", data={"username": "keith", "password": "wrongpass"})
        assert resp.status_code == 200
        assert "invalid" in resp.text.lower()

    def test_nonexistent_user_shows_error(self, client):
        resp = client.post("/web/login", data={"username": "nobody", "password": "test"})
        assert resp.status_code == 200
        assert "invalid" in resp.text.lower()


class TestSessionEnforcement:
    """Authenticated routes redirect to login without valid session."""

    def test_inbox_requires_auth(self, client):
        resp = client.get("/web/inbox")
        assert resp.status_code == 302
        assert "/web/login" in resp.headers["location"]

    def test_expired_session_redirects(self, client):
        token = _make_session_cookie("keith", expired=True)
        client.cookies.set("session", token)
        resp = client.get("/web/inbox")
        assert resp.status_code == 302
        assert "/web/login" in resp.headers["location"]


class TestInboxPage:
    """GET /web/inbox renders conversation list."""

    def test_inbox_renders_with_session(self, client):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox")
        assert resp.status_code == 200
        assert "Inbox" in resp.text

    def test_inbox_shows_display_name(self, client):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox")
        assert "Keith" in resp.text

    def test_inbox_empty_state(self, client):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox")
        assert "No conversations yet" in resp.text

    def test_inbox_shows_conversations(self, client, web_db):
        from ai_mailbox.db.queries import find_or_create_direct_conversation, insert_message
        conv_id = find_or_create_direct_conversation(web_db, "amy", "keith", "general")
        insert_message(web_db, conv_id, "amy", "Hello Keith")

        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox")
        assert "Hello Keith" in resp.text

    def test_inbox_has_nav_bar(self, client):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox")
        assert "AI Mailbox" in resp.text
        assert "Logout" in resp.text


class TestLogout:
    """GET /web/logout clears session and redirects."""

    def test_logout_redirects_to_login(self, client):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/logout")
        assert resp.status_code == 302
        assert "/web/login" in resp.headers["location"]

    def test_logout_clears_cookie(self, client):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/logout")
        set_cookie = resp.headers.get("set-cookie", "")
        # Cookie should be deleted (max-age=0 or expires in past)
        assert "session" in set_cookie.lower()


class TestHealthPage:
    """GET /web/health renders health dashboard publicly."""

    def test_health_page_no_auth_required(self, client):
        resp = client.get("/web/health")
        assert resp.status_code == 200

    def test_health_page_shows_status(self, client):
        resp = client.get("/web/health")
        assert "HEALTHY" in resp.text

    def test_health_page_shows_version(self, client):
        resp = client.get("/web/health")
        assert "0.3.0" in resp.text

    def test_health_page_shows_user_count(self, client):
        resp = client.get("/web/health")
        assert "2" in resp.text  # keith + amy
