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

    def test_login_page_has_semantic_ui(self, client):
        resp = client.get("/web/login")
        assert "semantic" in resp.text.lower()

    def test_login_page_no_tailwind(self, client):
        resp = client.get("/web/login")
        assert "tailwindcss" not in resp.text

    def test_login_page_has_jquery(self, client):
        resp = client.get("/web/login")
        assert "jquery" in resp.text.lower()

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
    """GET /web/inbox renders two-panel layout."""

    def test_inbox_renders_with_session(self, client):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox")
        assert resp.status_code == 200

    def test_inbox_shows_display_name(self, client):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox")
        assert "Keith" in resp.text

    def test_inbox_has_sidebar(self, client):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox")
        assert 'id="sidebar"' in resp.text
        assert 'id="conversation-list"' in resp.text

    def test_inbox_has_main_content(self, client):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox")
        assert 'id="main-content"' in resp.text

    def test_inbox_has_empty_state(self, client):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox")
        assert "Select a conversation" in resp.text

    def test_inbox_has_nav_bar(self, client):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox")
        assert "AI Mailbox" in resp.text
        assert "Logout" in resp.text

    def test_inbox_has_compose_link(self, client):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox")
        assert "Compose" in resp.text


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
        assert "0.4.0" in resp.text

    def test_health_page_shows_user_count(self, client):
        resp = client.get("/web/health")
        assert "2" in resp.text  # keith + amy


# ---------------------------------------------------------------------------
# Sprint 2: Login rate limiting
# ---------------------------------------------------------------------------

class TestLoginRateLimit:
    """POST /web/login rate limited to 5/minute per IP."""

    def test_rate_limit_after_5_attempts(self, client):
        from ai_mailbox.rate_limit import reset_storage
        reset_storage()
        for _ in range(5):
            client.post("/web/login", data={"username": "x", "password": "y"})
        resp = client.post("/web/login", data={"username": "x", "password": "y"})
        assert resp.status_code == 429
        assert "too many" in resp.text.lower()

    def test_rate_limit_shows_on_login_page(self, client):
        from ai_mailbox.rate_limit import reset_storage
        reset_storage()
        for _ in range(5):
            client.post("/web/login", data={"username": "x", "password": "y"})
        resp = client.post("/web/login", data={"username": "x", "password": "y"})
        assert "login" in resp.text.lower()  # Still renders the login template


# ---------------------------------------------------------------------------
# Sprint 2: Inbox pagination
# ---------------------------------------------------------------------------

class TestConversationListPartial:
    """GET /web/inbox/conversations returns sidebar content."""

    def _seed(self, web_db, count=3):
        from ai_mailbox.db.queries import find_or_create_direct_conversation, insert_message
        ids = []
        for i in range(count):
            conv_id = find_or_create_direct_conversation(web_db, "amy", "keith", f"proj-{i:03d}")
            insert_message(web_db, conv_id, "amy", f"Message in proj-{i:03d}")
            ids.append(conv_id)
        return ids

    def test_requires_auth(self, client):
        resp = client.get("/web/inbox/conversations")
        assert resp.status_code == 302

    def test_returns_conversations(self, client, web_db):
        self._seed(web_db)
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox/conversations")
        assert resp.status_code == 200
        assert "amy" in resp.text.lower()

    def test_shows_unread_badge(self, client, web_db):
        from ai_mailbox.db.queries import find_or_create_direct_conversation, insert_message
        conv_id = find_or_create_direct_conversation(web_db, "amy", "keith", "general")
        insert_message(web_db, conv_id, "amy", "Unread 1")
        insert_message(web_db, conv_id, "amy", "Unread 2")
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox/conversations")
        assert "2" in resp.text

    def test_shows_project_label(self, client, web_db):
        from ai_mailbox.db.queries import find_or_create_direct_conversation, insert_message
        conv_id = find_or_create_direct_conversation(web_db, "amy", "keith", "deployment")
        insert_message(web_db, conv_id, "amy", "Deploy ready")
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox/conversations")
        assert "deployment" in resp.text

    def test_filter_by_project(self, client, web_db):
        from ai_mailbox.db.queries import find_or_create_direct_conversation, insert_message
        find_or_create_direct_conversation(web_db, "amy", "keith", "general")
        conv2 = find_or_create_direct_conversation(web_db, "amy", "keith", "alerts")
        insert_message(web_db, conv2, "amy", "Alert msg")
        # Also seed general with a message
        conv1 = find_or_create_direct_conversation(web_db, "amy", "keith", "general")
        insert_message(web_db, conv1, "amy", "General msg")
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox/conversations?project=alerts")
        assert "Alert msg" in resp.text
        assert "General msg" not in resp.text

    def test_pagination_load_more(self, client, web_db):
        self._seed(web_db, 25)
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox/conversations")
        assert "Load more" in resp.text

    def test_empty_state(self, client, web_db):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox/conversations")
        assert "No conversations found" in resp.text


# ---------------------------------------------------------------------------
# Sprint 2: Thread view
# ---------------------------------------------------------------------------

class TestThreadView:
    """GET /web/conversation/{conv_id} shows messages."""

    def _seed_conversation(self, web_db):
        from ai_mailbox.db.queries import find_or_create_direct_conversation, insert_message
        conv_id = find_or_create_direct_conversation(web_db, "keith", "amy", "general")
        insert_message(web_db, conv_id, "keith", "Hello Amy")
        insert_message(web_db, conv_id, "amy", "Hi Keith")
        insert_message(web_db, conv_id, "keith", "How are you?")
        return conv_id

    def test_requires_auth(self, client, web_db):
        conv_id = self._seed_conversation(web_db)
        resp = client.get(f"/web/conversation/{conv_id}")
        assert resp.status_code == 302

    def test_shows_messages(self, client, web_db):
        conv_id = self._seed_conversation(web_db)
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get(f"/web/conversation/{conv_id}")
        assert resp.status_code == 200
        assert "Hello Amy" in resp.text
        assert "Hi Keith" in resp.text
        assert "How are you?" in resp.text

    def test_shows_message_authors(self, client, web_db):
        conv_id = self._seed_conversation(web_db)
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get(f"/web/conversation/{conv_id}")
        assert "keith" in resp.text
        assert "amy" in resp.text

    def test_marks_as_read(self, client, web_db):
        from ai_mailbox.db.queries import get_last_read_sequence
        conv_id = self._seed_conversation(web_db)
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        # Before viewing: cursor is 0
        assert get_last_read_sequence(web_db, conv_id, "keith") == 0
        client.get(f"/web/conversation/{conv_id}")
        # After viewing: cursor advanced to 3
        assert get_last_read_sequence(web_db, conv_id, "keith") == 3

    def test_has_reply_form(self, client, web_db):
        conv_id = self._seed_conversation(web_db)
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get(f"/web/conversation/{conv_id}")
        assert "Reply" in resp.text
        assert "textarea" in resp.text.lower()

    def test_nonexistent_conversation(self, client, web_db):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/conversation/nonexistent-id")
        assert resp.status_code == 404

    def test_non_participant_denied(self, client, web_db):
        conv_id = self._seed_conversation(web_db)
        # Create bob
        web_db._conn.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("bob", "Bob", "bob-key"),
        )
        web_db._conn.commit()
        pw_hash = hash_password("bobpass")
        web_db._conn.execute("UPDATE users SET password_hash = ? WHERE id = 'bob'", (pw_hash,))
        web_db._conn.commit()
        token = _make_session_cookie("bob")
        client.cookies.set("session", token)
        resp = client.get(f"/web/conversation/{conv_id}")
        assert resp.status_code == 403

    def test_shows_project_label(self, client, web_db):
        conv_id = self._seed_conversation(web_db)
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get(f"/web/conversation/{conv_id}")
        assert "general" in resp.text


# ---------------------------------------------------------------------------
# Sprint 2: Reply
# ---------------------------------------------------------------------------

class TestReply:
    """POST /web/conversation/{conv_id}/reply posts a reply."""

    def _seed_conversation(self, web_db):
        from ai_mailbox.db.queries import find_or_create_direct_conversation, insert_message
        conv_id = find_or_create_direct_conversation(web_db, "keith", "amy", "general")
        insert_message(web_db, conv_id, "amy", "Hello Keith")
        return conv_id

    def test_requires_auth(self, client, web_db):
        conv_id = self._seed_conversation(web_db)
        resp = client.post(f"/web/conversation/{conv_id}/reply", data={"body": "reply"})
        assert resp.status_code == 302

    def test_reply_adds_message(self, client, web_db):
        conv_id = self._seed_conversation(web_db)
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.post(f"/web/conversation/{conv_id}/reply", data={"body": "Thanks!"})
        assert resp.status_code == 200
        assert "Thanks!" in resp.text

    def test_empty_body_shows_error(self, client, web_db):
        conv_id = self._seed_conversation(web_db)
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.post(f"/web/conversation/{conv_id}/reply", data={"body": ""})
        assert resp.status_code == 200
        assert "empty" in resp.text.lower()

    def test_reply_marks_as_read(self, client, web_db):
        from ai_mailbox.db.queries import get_last_read_sequence
        conv_id = self._seed_conversation(web_db)
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        client.post(f"/web/conversation/{conv_id}/reply", data={"body": "My reply"})
        # After reply: cursor should be at 2 (original + reply)
        assert get_last_read_sequence(web_db, conv_id, "keith") == 2

    def test_nonexistent_conversation(self, client, web_db):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.post("/web/conversation/fake-id/reply", data={"body": "reply"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Sprint 2: Compose
# ---------------------------------------------------------------------------

class TestCompose:
    """GET/POST /web/compose creates new messages."""

    def test_compose_get_requires_auth(self, client):
        resp = client.get("/web/compose")
        assert resp.status_code == 302

    def test_compose_shows_form(self, client, web_db):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/compose", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "New Message" in resp.text
        assert "amy" in resp.text.lower()  # recipient dropdown

    def test_compose_excludes_self(self, client, web_db):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/compose", headers={"HX-Request": "true"})
        # keith should NOT be in the recipient list
        assert 'value="keith"' not in resp.text

    def test_compose_post_requires_auth(self, client):
        resp = client.post("/web/compose", data={"to": "amy", "body": "hi"})
        assert resp.status_code == 302

    def test_compose_send_success(self, client, web_db):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.post("/web/compose", data={
            "to": "amy", "body": "Hello Amy!", "project": "general",
        })
        assert resp.status_code == 200
        # Should show thread view with the sent message
        assert "Hello Amy!" in resp.text

    def test_compose_empty_body_error(self, client, web_db):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.post("/web/compose", data={
            "to": "amy", "body": "", "project": "general",
        })
        assert resp.status_code == 200
        assert "empty" in resp.text.lower()

    def test_compose_missing_recipient_error(self, client, web_db):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.post("/web/compose", data={
            "to": "", "body": "hello", "project": "general",
        })
        assert resp.status_code == 200
        assert "recipient" in resp.text.lower()

    def test_compose_self_send_error(self, client, web_db):
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.post("/web/compose", data={
            "to": "keith", "body": "self msg", "project": "general",
        })
        assert resp.status_code == 200
        assert "yourself" in resp.text.lower()

    def test_compose_reuses_existing_conversation(self, client, web_db):
        from ai_mailbox.db.queries import find_or_create_direct_conversation, insert_message
        # Pre-create conversation with a message
        conv_id = find_or_create_direct_conversation(web_db, "keith", "amy", "general")
        insert_message(web_db, conv_id, "amy", "Existing message")
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.post("/web/compose", data={
            "to": "amy", "body": "New message", "project": "general",
        })
        # Should show both messages (reused conversation)
        assert "Existing message" in resp.text
        assert "New message" in resp.text


# ---------------------------------------------------------------------------
# Sprint 2: Filter dropdown clearability and sidebar refresh
# ---------------------------------------------------------------------------

class TestFilterDropdowns:
    """Filter dropdowns must be clearable and sidebar refresh must preserve filters."""

    def test_inbox_has_clear_filters_link(self, client):
        """Inbox should have a clear-filters link and clearable dropdown init."""
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get("/web/inbox")
        assert "clear-filters" in resp.text
        assert "clearable" in resp.text

    def test_thread_view_sidebar_refresh_reads_filters(self, client, web_db):
        """Thread view should NOT hardcode a bare /web/inbox/conversations hx-get.

        Instead it should use JS to read the current filter values from the dropdowns.
        """
        from ai_mailbox.db.queries import find_or_create_direct_conversation, insert_message
        conv_id = find_or_create_direct_conversation(web_db, "keith", "amy", "general")
        insert_message(web_db, conv_id, "keith", "test msg")
        token = _make_session_cookie("keith")
        client.cookies.set("session", token)
        resp = client.get(f"/web/conversation/{conv_id}", headers={"HX-Request": "true"})
        # Should NOT have a bare hx-get that drops filter params
        assert 'hx-get="/web/inbox/conversations"' not in resp.text
        # Should reference filter elements to preserve state
        assert "project-filter" in resp.text
