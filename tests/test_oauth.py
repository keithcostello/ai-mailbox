"""Test Suite: OAuth Provider — token and auth code management."""

import json
import time
import pytest

from ai_mailbox.oauth import (
    MailboxOAuthProvider,
    _parse_scopes,
    hash_password,
    verify_password,
)


class TestParseScopes:
    """Scopes normalization: JSON array and comma-separated backward compat."""

    def test_json_array(self):
        assert _parse_scopes('["read", "write"]') == ["read", "write"]

    def test_comma_separated(self):
        assert _parse_scopes("read,write") == ["read", "write"]

    def test_comma_separated_with_spaces(self):
        assert _parse_scopes("read, write, admin") == ["read", "write", "admin"]

    def test_empty_string(self):
        assert _parse_scopes("") == []

    def test_none(self):
        assert _parse_scopes(None) == []

    def test_single_scope_json(self):
        assert _parse_scopes('["read"]') == ["read"]

    def test_single_scope_plain(self):
        assert _parse_scopes("read") == ["read"]

    def test_empty_json_array(self):
        assert _parse_scopes("[]") == []


@pytest.fixture
def provider(db):
    """OAuth provider backed by test DB."""
    return MailboxOAuthProvider(db=db, jwt_secret="test-secret-key-for-jwt")


def test_hash_password_and_verify():
    """bcrypt hashing works round-trip."""
    pw_hash = hash_password("mypassword")
    assert verify_password("mypassword", pw_hash)
    assert not verify_password("wrongpassword", pw_hash)


def test_create_and_load_access_token(provider):
    """Token created for user can be loaded back with user_id."""
    token_str = provider.create_user_token(user_id="keith", client_id="test-client")
    loaded = provider.load_user_from_token(token_str)
    assert loaded == "keith"


def test_create_token_for_amy(provider):
    """Amy's token returns amy user_id."""
    token_str = provider.create_user_token(user_id="amy", client_id="test-client")
    loaded = provider.load_user_from_token(token_str)
    assert loaded == "amy"


def test_expired_token_rejected(provider):
    """Token with past expiry returns None."""
    token_str = provider.create_user_token(
        user_id="keith", client_id="test-client", expires_in=-1
    )
    loaded = provider.load_user_from_token(token_str)
    assert loaded is None


def test_invalid_token_rejected(provider):
    """Garbage string returns None."""
    loaded = provider.load_user_from_token("not-a-valid-token")
    assert loaded is None


def test_wrong_secret_rejected():
    """Token signed with different secret is rejected."""
    from ai_mailbox.db.connection import SQLiteDB
    import sqlite3
    from ai_mailbox.db.schema import ensure_schema_sqlite

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema_sqlite(conn)
    db = SQLiteDB(conn)

    provider1 = MailboxOAuthProvider(db=db, jwt_secret="secret-A")
    provider2 = MailboxOAuthProvider(db=db, jwt_secret="secret-B")

    token = provider1.create_user_token(user_id="keith", client_id="test")
    loaded = provider2.load_user_from_token(token)
    assert loaded is None


@pytest.mark.asyncio
async def test_register_and_get_client(provider):
    """Dynamic client registration stores and retrieves client."""
    from mcp.shared.auth import OAuthClientInformationFull

    client_info = OAuthClientInformationFull(
        client_id="test-client-123",
        client_name="Test Client",
        redirect_uris=["http://localhost:3000/callback"],
        grant_types=["authorization_code"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )
    await provider.register_client(client_info)
    loaded = await provider.get_client("test-client-123")
    assert loaded is not None
    assert loaded.client_name == "Test Client"


@pytest.mark.asyncio
async def test_get_nonexistent_client(provider):
    """Getting a non-existent client returns None."""
    loaded = await provider.get_client("nonexistent")
    assert loaded is None
