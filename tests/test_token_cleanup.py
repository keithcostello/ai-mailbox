"""Tests for token_cleanup -- expired OAuth code and token deletion."""

import time

import pytest

from ai_mailbox.token_cleanup import cleanup_expired_tokens


def _seed_oauth_client(db):
    """Insert a test OAuth client required by foreign-key-free convention."""
    db.execute(
        "INSERT OR IGNORE INTO oauth_clients (client_id, client_info) VALUES (?, ?)",
        ("test-client", "{}"),
    )


def _insert_code(db, code, expires_at):
    db.execute(
        "INSERT INTO oauth_codes "
        "(code, client_id, user_id, code_challenge, redirect_uri, scopes, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (code, "test-client", "keith", "challenge", "http://localhost", "read", expires_at),
    )


def _insert_token(db, token, expires_at):
    db.execute(
        "INSERT INTO oauth_tokens "
        "(token, client_id, user_id, scopes, expires_at, refresh_token) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (token, "test-client", "keith", "read", expires_at, None),
    )


# ---------- codes ----------


def test_cleanup_deletes_expired_codes(db):
    _seed_oauth_client(db)
    _insert_code(db, "expired-1", time.time() - 600)
    _insert_code(db, "expired-2", time.time() - 1200)

    result = cleanup_expired_tokens(db)

    assert result["codes_deleted"] == 2
    remaining = db.fetchall("SELECT code FROM oauth_codes")
    assert remaining == []


def test_cleanup_preserves_valid_codes(db):
    _seed_oauth_client(db)
    _insert_code(db, "future-code", time.time() + 3600)

    result = cleanup_expired_tokens(db)

    assert result["codes_deleted"] == 0
    remaining = db.fetchall("SELECT code FROM oauth_codes")
    assert len(remaining) == 1
    assert remaining[0]["code"] == "future-code"


# ---------- tokens ----------


def test_cleanup_deletes_expired_tokens(db):
    _seed_oauth_client(db)
    _insert_token(db, "expired-tok-1", int(time.time()) - 600)
    _insert_token(db, "expired-tok-2", int(time.time()) - 1200)

    result = cleanup_expired_tokens(db)

    assert result["tokens_deleted"] == 2
    remaining = db.fetchall("SELECT token FROM oauth_tokens")
    assert remaining == []


def test_cleanup_preserves_valid_tokens(db):
    _seed_oauth_client(db)
    _insert_token(db, "valid-tok", int(time.time()) + 7200)

    result = cleanup_expired_tokens(db)

    assert result["tokens_deleted"] == 0
    remaining = db.fetchall("SELECT token FROM oauth_tokens")
    assert len(remaining) == 1
    assert remaining[0]["token"] == "valid-tok"


def test_cleanup_preserves_tokens_without_expiry(db):
    _seed_oauth_client(db)
    db.execute(
        "INSERT INTO oauth_tokens "
        "(token, client_id, user_id, scopes, expires_at, refresh_token) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("no-expiry-tok", "test-client", "keith", "read", None, None),
    )

    result = cleanup_expired_tokens(db)

    assert result["tokens_deleted"] == 0
    remaining = db.fetchall("SELECT token FROM oauth_tokens")
    assert len(remaining) == 1
    assert remaining[0]["token"] == "no-expiry-tok"


# ---------- edge cases ----------


def test_cleanup_empty_tables(db):
    result = cleanup_expired_tokens(db)

    assert result == {"codes_deleted": 0, "tokens_deleted": 0}


def test_cleanup_returns_correct_counts(db):
    _seed_oauth_client(db)
    for i in range(3):
        _insert_code(db, f"exp-code-{i}", time.time() - 100 * (i + 1))
    for i in range(2):
        _insert_token(db, f"exp-tok-{i}", int(time.time()) - 100 * (i + 1))

    result = cleanup_expired_tokens(db)

    assert result["codes_deleted"] == 3
    assert result["tokens_deleted"] == 2


def test_cleanup_mixed_expired_and_valid(db):
    _seed_oauth_client(db)
    # Expired codes
    _insert_code(db, "old-code-1", time.time() - 900)
    _insert_code(db, "old-code-2", time.time() - 1800)
    # Valid code
    _insert_code(db, "fresh-code", time.time() + 3600)

    # Expired token
    _insert_token(db, "old-tok", int(time.time()) - 300)
    # Valid token
    _insert_token(db, "fresh-tok", int(time.time()) + 7200)
    # No-expiry token
    db.execute(
        "INSERT INTO oauth_tokens "
        "(token, client_id, user_id, scopes, expires_at, refresh_token) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("forever-tok", "test-client", "keith", "read", None, None),
    )

    result = cleanup_expired_tokens(db)

    assert result["codes_deleted"] == 2
    assert result["tokens_deleted"] == 1

    codes = db.fetchall("SELECT code FROM oauth_codes")
    assert len(codes) == 1
    assert codes[0]["code"] == "fresh-code"

    tokens = db.fetchall("SELECT token FROM oauth_tokens ORDER BY token")
    assert len(tokens) == 2
    token_names = sorted(t["token"] for t in tokens)
    assert token_names == ["forever-tok", "fresh-tok"]
