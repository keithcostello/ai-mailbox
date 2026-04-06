"""Tests for GitHub OAuth registration flow -- web_oauth routes."""

import sqlite3
import time
from unittest.mock import AsyncMock, patch, MagicMock

import jwt
import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette

from ai_mailbox.config import Config
from ai_mailbox.db.connection import SQLiteDB
from ai_mailbox.oauth import MailboxOAuthProvider, hash_password

JWT_SECRET = "test-secret-for-oauth-minimum-32-bytes!!"

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


@pytest.fixture
def oauth_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA_SQL)
    conn.execute(
        "INSERT INTO users (id, display_name, api_key, password_hash) VALUES (?, ?, ?, ?)",
        ("keith", "Keith", "test-key", hash_password("testpass")),
    )
    conn.commit()
    yield SQLiteDB(conn)
    conn.close()


@pytest.fixture
def oauth_config():
    return Config(
        jwt_secret=JWT_SECRET,
        github_client_id="test-github-id",
        github_client_secret="test-github-secret",
        invite_only=True,
    )


@pytest.fixture
def oauth_config_no_github():
    return Config(jwt_secret=JWT_SECRET, invite_only=False)


@pytest.fixture
def oauth_app(oauth_db, oauth_config):
    from ai_mailbox.web_oauth import create_oauth_routes
    provider = MailboxOAuthProvider(db=oauth_db, jwt_secret=JWT_SECRET)
    routes = create_oauth_routes(oauth_db, provider, oauth_config, JWT_SECRET)
    app = Starlette(routes=routes)
    return app


@pytest.fixture
def oauth_client(oauth_app):
    return TestClient(oauth_app, follow_redirects=False)


# --- find_or_create_oauth_user tests ---

class TestFindOrCreateOAuthUser:
    def test_creates_new_user(self, oauth_db):
        from ai_mailbox.web_oauth import find_or_create_oauth_user
        uid = find_or_create_oauth_user(
            oauth_db, email="alice@example.com", name="Alice",
            avatar_url="https://example.com/alice.png", provider="github",
        )
        assert uid.startswith("gh-")
        row = oauth_db.fetchone("SELECT * FROM users WHERE id = ?", (uid,))
        assert row["display_name"] == "Alice"
        assert row["email"] == "alice@example.com"
        assert row["auth_provider"] == "github"
        assert row["avatar_url"] == "https://example.com/alice.png"

    def test_returns_existing_user(self, oauth_db):
        from ai_mailbox.web_oauth import find_or_create_oauth_user
        uid1 = find_or_create_oauth_user(
            oauth_db, email="bob@example.com", name="Bob",
            avatar_url=None, provider="github",
        )
        uid2 = find_or_create_oauth_user(
            oauth_db, email="bob@example.com", name="Bob Updated",
            avatar_url="https://new.png", provider="github",
        )
        assert uid1 == uid2
        row = oauth_db.fetchone("SELECT * FROM users WHERE id = ?", (uid1,))
        assert row["display_name"] == "Bob Updated"
        assert row["avatar_url"] == "https://new.png"

    def test_different_providers_different_users(self, oauth_db):
        from ai_mailbox.web_oauth import find_or_create_oauth_user
        uid_gh = find_or_create_oauth_user(
            oauth_db, email="sam@example.com", name="Sam",
            avatar_url=None, provider="github",
        )
        # Simulate a future google provider
        oauth_db.execute(
            "INSERT INTO users (id, display_name, api_key, email, auth_provider) VALUES (?, ?, ?, ?, ?)",
            ("g-sam", "Sam G", "oauth-g-sam", "sam@example.com", "google"),
        )
        oauth_db.commit()
        row_gh = oauth_db.fetchone("SELECT * FROM users WHERE id = ?", (uid_gh,))
        assert row_gh["auth_provider"] == "github"

    def test_user_id_collision_resolved(self, oauth_db):
        """If gh-alice already exists, new user gets gh-alice-2."""
        from ai_mailbox.web_oauth import find_or_create_oauth_user
        # Pre-create a user with the expected ID
        oauth_db.execute(
            "INSERT INTO users (id, display_name, api_key, email, auth_provider) VALUES (?, ?, ?, ?, ?)",
            ("gh-alice", "Alice OG", "oauth-gh-alice", "alice-og@example.com", "github"),
        )
        oauth_db.commit()
        uid = find_or_create_oauth_user(
            oauth_db, email="alice@different.com", name="Alice New",
            avatar_url=None, provider="github",
        )
        assert uid == "gh-alice-2"


# --- Invite check tests ---

class TestInviteCheck:
    def test_invited_email_allowed(self, oauth_db):
        from ai_mailbox.web_oauth import check_invite
        oauth_db.execute(
            "INSERT INTO user_invites (email, invited_by) VALUES (?, ?)",
            ("invited@example.com", "keith"),
        )
        oauth_db.commit()
        assert check_invite(oauth_db, "invited@example.com", "github") is True

    def test_uninvited_email_rejected(self, oauth_db):
        from ai_mailbox.web_oauth import check_invite
        assert check_invite(oauth_db, "stranger@example.com", "github") is False

    def test_existing_user_always_allowed(self, oauth_db):
        """A previously registered user can always log in."""
        from ai_mailbox.web_oauth import find_or_create_oauth_user, check_invite
        find_or_create_oauth_user(
            oauth_db, email="member@example.com", name="Member",
            avatar_url=None, provider="github",
        )
        # Not in invites table, but already a user
        assert check_invite(oauth_db, "member@example.com", "github") is True

    def test_invite_marked_used(self, oauth_db):
        from ai_mailbox.web_oauth import mark_invite_used
        oauth_db.execute(
            "INSERT INTO user_invites (email, invited_by) VALUES (?, ?)",
            ("new@example.com", "keith"),
        )
        oauth_db.commit()
        mark_invite_used(oauth_db, "new@example.com")
        row = oauth_db.fetchone("SELECT used_at FROM user_invites WHERE email = ?", ("new@example.com",))
        assert row["used_at"] is not None


# --- OAuth route tests ---

class TestOAuthRoutes:
    def test_github_initiate_redirects(self, oauth_client):
        resp = oauth_client.get("/web/oauth/github")
        assert resp.status_code == 302
        location = resp.headers["location"]
        assert "github.com/login/oauth/authorize" in location
        assert "test-github-id" in location

    def test_github_initiate_sets_state_cookie(self, oauth_client):
        resp = oauth_client.get("/web/oauth/github")
        assert "oauth_state" in resp.cookies or any(
            "oauth_state" in c for c in resp.headers.getlist("set-cookie")
        )

    def test_callback_without_code_errors(self, oauth_client):
        resp = oauth_client.get("/web/oauth/callback?state=bad")
        assert resp.status_code == 302
        assert "error" in resp.headers["location"]

    def test_callback_state_mismatch_errors(self, oauth_client):
        # First initiate to get a valid state
        resp = oauth_client.get("/web/oauth/github")
        # Now callback with wrong state
        resp2 = oauth_client.get("/web/oauth/callback?code=testcode&state=wrong")
        assert resp2.status_code == 302
        assert "error" in resp2.headers["location"]


class TestOAuthCallbackIntegration:
    """Test the full callback flow with mocked GitHub API."""

    def _mock_github_responses(self):
        """Return mock for GitHub token + user info responses."""
        token_resp = MagicMock()
        token_resp.json.return_value = {"access_token": "gho_test123", "token_type": "bearer"}
        token_resp.raise_for_status = MagicMock()

        user_resp = MagicMock()
        user_resp.json.return_value = {
            "login": "testdev",
            "name": "Test Developer",
            "avatar_url": "https://avatars.githubusercontent.com/testdev",
        }
        user_resp.raise_for_status = MagicMock()

        emails_resp = MagicMock()
        emails_resp.json.return_value = [
            {"email": "testdev@example.com", "primary": True, "verified": True},
        ]
        emails_resp.raise_for_status = MagicMock()

        return token_resp, user_resp, emails_resp

    def test_new_user_redirects_to_pick_handle(self, oauth_db, oauth_config):
        """New user: callback redirects to pick-handle page, not inbox."""
        from ai_mailbox.web_oauth import create_oauth_routes
        provider = MailboxOAuthProvider(db=oauth_db, jwt_secret=JWT_SECRET)

        oauth_db.execute(
            "INSERT INTO user_invites (email, invited_by) VALUES (?, ?)",
            ("testdev@example.com", "keith"),
        )
        oauth_db.commit()

        routes = create_oauth_routes(oauth_db, provider, oauth_config, JWT_SECRET)
        app = Starlette(routes=routes)
        client = TestClient(app, follow_redirects=False)

        resp = client.get("/web/oauth/github")
        import urllib.parse
        parsed = urllib.parse.urlparse(resp.headers["location"])
        params = urllib.parse.parse_qs(parsed.query)
        state = params["state"][0]

        token_resp, user_resp, emails_resp = self._mock_github_responses()

        with patch("ai_mailbox.web_oauth.httpx") as mock_httpx:
            mock_httpx.post.return_value = token_resp
            mock_httpx.get.side_effect = [user_resp, emails_resp]
            resp2 = client.get(f"/web/oauth/callback?code=testcode&state={state}")

        assert resp2.status_code == 302
        assert "/web/oauth/pick-handle" in resp2.headers["location"]

    def test_pick_handle_creates_user(self, oauth_db, oauth_config):
        """Full flow: callback -> pick-handle -> user created with chosen handle."""
        from ai_mailbox.web_oauth import create_oauth_routes
        provider = MailboxOAuthProvider(db=oauth_db, jwt_secret=JWT_SECRET)

        oauth_db.execute(
            "INSERT INTO user_invites (email, invited_by) VALUES (?, ?)",
            ("testdev@example.com", "keith"),
        )
        oauth_db.commit()

        routes = create_oauth_routes(oauth_db, provider, oauth_config, JWT_SECRET)
        app = Starlette(routes=routes)
        client = TestClient(app, follow_redirects=False)

        # Initiate + callback
        resp = client.get("/web/oauth/github")
        import urllib.parse
        parsed = urllib.parse.urlparse(resp.headers["location"])
        params = urllib.parse.parse_qs(parsed.query)
        state = params["state"][0]

        token_resp, user_resp, emails_resp = self._mock_github_responses()
        with patch("ai_mailbox.web_oauth.httpx") as mock_httpx:
            mock_httpx.post.return_value = token_resp
            mock_httpx.get.side_effect = [user_resp, emails_resp]
            resp2 = client.get(f"/web/oauth/callback?code=testcode&state={state}")

        # Extract registration token from redirect
        parsed2 = urllib.parse.urlparse(resp2.headers["location"])
        reg_token = urllib.parse.parse_qs(parsed2.query)["token"][0]

        # GET pick-handle page
        resp3 = client.get(f"/web/oauth/pick-handle?token={reg_token}")
        assert resp3.status_code == 200
        assert "Pick" in resp3.text or "username" in resp3.text.lower()

        # POST chosen handle
        resp4 = client.post("/web/oauth/pick-handle", data={"token": reg_token, "handle": "testdev"})
        assert resp4.status_code == 302
        assert resp4.headers["location"] == "/web/inbox"

        # User created with chosen handle
        row = oauth_db.fetchone("SELECT * FROM users WHERE id = 'testdev'")
        assert row is not None
        assert row["email"] == "testdev@example.com"
        assert row["auth_provider"] == "github"
        assert row["display_name"] == "Test Developer"

    def test_pick_handle_rejects_taken_name(self, oauth_db, oauth_config):
        """Can't pick a handle that's already taken."""
        from ai_mailbox.web_oauth import create_oauth_routes
        provider = MailboxOAuthProvider(db=oauth_db, jwt_secret=JWT_SECRET)

        oauth_db.execute(
            "INSERT INTO user_invites (email, invited_by) VALUES (?, ?)",
            ("testdev@example.com", "keith"),
        )
        oauth_db.commit()

        routes = create_oauth_routes(oauth_db, provider, oauth_config, JWT_SECRET)
        app = Starlette(routes=routes)
        client = TestClient(app, follow_redirects=False)

        resp = client.get("/web/oauth/github")
        import urllib.parse
        parsed = urllib.parse.urlparse(resp.headers["location"])
        state = urllib.parse.parse_qs(parsed.query)["state"][0]

        token_resp, user_resp, emails_resp = self._mock_github_responses()
        with patch("ai_mailbox.web_oauth.httpx") as mock_httpx:
            mock_httpx.post.return_value = token_resp
            mock_httpx.get.side_effect = [user_resp, emails_resp]
            resp2 = client.get(f"/web/oauth/callback?code=testcode&state={state}")

        parsed2 = urllib.parse.urlparse(resp2.headers["location"])
        reg_token = urllib.parse.parse_qs(parsed2.query)["token"][0]

        # "keith" already exists
        resp4 = client.post("/web/oauth/pick-handle", data={"token": reg_token, "handle": "keith"})
        assert resp4.status_code == 200
        assert "taken" in resp4.text.lower()

    def test_returning_user_skips_pick_handle(self, oauth_db, oauth_config):
        """Existing user logs in directly without seeing pick-handle."""
        from ai_mailbox.web_oauth import create_oauth_routes, create_oauth_user
        provider = MailboxOAuthProvider(db=oauth_db, jwt_secret=JWT_SECRET)

        # Pre-register user
        create_oauth_user(
            oauth_db, user_id="testdev", email="testdev@example.com",
            name="Test Developer", avatar_url=None, provider="github",
        )

        routes = create_oauth_routes(oauth_db, provider, oauth_config, JWT_SECRET)
        app = Starlette(routes=routes)
        client = TestClient(app, follow_redirects=False)

        resp = client.get("/web/oauth/github")
        import urllib.parse
        parsed = urllib.parse.urlparse(resp.headers["location"])
        state = urllib.parse.parse_qs(parsed.query)["state"][0]

        token_resp, user_resp, emails_resp = self._mock_github_responses()
        with patch("ai_mailbox.web_oauth.httpx") as mock_httpx:
            mock_httpx.post.return_value = token_resp
            mock_httpx.get.side_effect = [user_resp, emails_resp]
            resp2 = client.get(f"/web/oauth/callback?code=testcode&state={state}")

        assert resp2.status_code == 302
        assert resp2.headers["location"] == "/web/inbox"

    def test_uninvited_user_rejected(self, oauth_db, oauth_config):
        """Callback rejects user not in invite list."""
        from ai_mailbox.web_oauth import create_oauth_routes
        provider = MailboxOAuthProvider(db=oauth_db, jwt_secret=JWT_SECRET)
        routes = create_oauth_routes(oauth_db, provider, oauth_config, JWT_SECRET)
        app = Starlette(routes=routes)
        client = TestClient(app, follow_redirects=False)

        # Initiate
        resp = client.get("/web/oauth/github")
        import urllib.parse
        parsed = urllib.parse.urlparse(resp.headers["location"])
        params = urllib.parse.parse_qs(parsed.query)
        state = params["state"][0]

        token_resp, user_resp, emails_resp = self._mock_github_responses()

        with patch("ai_mailbox.web_oauth.httpx") as mock_httpx:
            mock_httpx.post.return_value = token_resp
            mock_httpx.get.side_effect = [user_resp, emails_resp]

            resp2 = client.get(f"/web/oauth/callback?code=testcode&state={state}")

        assert resp2.status_code == 302
        assert "not_invited" in resp2.headers["location"]

    def test_invite_not_required_when_disabled(self, oauth_db, oauth_config_no_github):
        """When invite_only=False, any GitHub user can reach pick-handle."""
        config = Config(
            jwt_secret=JWT_SECRET,
            github_client_id="test-github-id",
            github_client_secret="test-github-secret",
            invite_only=False,
        )
        from ai_mailbox.web_oauth import create_oauth_routes
        provider = MailboxOAuthProvider(db=oauth_db, jwt_secret=JWT_SECRET)
        routes = create_oauth_routes(oauth_db, provider, config, JWT_SECRET)
        app = Starlette(routes=routes)
        client = TestClient(app, follow_redirects=False)

        resp = client.get("/web/oauth/github")
        import urllib.parse
        parsed = urllib.parse.urlparse(resp.headers["location"])
        params = urllib.parse.parse_qs(parsed.query)
        state = params["state"][0]

        token_resp, user_resp, emails_resp = self._mock_github_responses()

        with patch("ai_mailbox.web_oauth.httpx") as mock_httpx:
            mock_httpx.post.return_value = token_resp
            mock_httpx.get.side_effect = [user_resp, emails_resp]

            resp2 = client.get(f"/web/oauth/callback?code=testcode&state={state}")

        assert resp2.status_code == 302
        assert "/web/oauth/pick-handle" in resp2.headers["location"]


# --- Config tests ---

class TestConfigOAuth:
    def test_github_oauth_available_when_configured(self):
        c = Config(github_client_id="id", github_client_secret="secret")
        assert c.github_oauth_available is True

    def test_github_oauth_unavailable_when_missing(self):
        c = Config()
        assert c.github_oauth_available is False

    def test_github_oauth_unavailable_partial(self):
        c = Config(github_client_id="id")
        assert c.github_oauth_available is False

    def test_invite_only_default_true(self):
        c = Config()
        assert c.invite_only is True

    def test_from_env_reads_github_vars(self, monkeypatch):
        monkeypatch.setenv("GITHUB_CLIENT_ID", "env-id")
        monkeypatch.setenv("GITHUB_CLIENT_SECRET", "env-secret")
        monkeypatch.setenv("MAILBOX_INVITE_ONLY", "false")
        monkeypatch.setenv("MAILBOX_INVITED_EMAILS", "a@b.com,c@d.com")
        monkeypatch.setenv("MAILBOX_JWT_SECRET", "x" * 32)
        c = Config.from_env()
        assert c.github_client_id == "env-id"
        assert c.github_client_secret == "env-secret"
        assert c.invite_only is False
        assert c.invited_emails == "a@b.com,c@d.com"
