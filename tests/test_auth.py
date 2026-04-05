"""Test Suite 1: OAuth Token-based Identity — 3 tests."""

import pytest

from ai_mailbox.oauth import MailboxOAuthProvider


@pytest.fixture
def provider(db):
    return MailboxOAuthProvider(db=db, jwt_secret="test-secret-key-minimum-32-bytes!")


def test_valid_token_returns_user_id(provider):
    """Token-based auth works."""
    token = provider.create_user_token(user_id="keith", client_id="test")
    assert provider.load_user_from_token(token) == "keith"


def test_invalid_token_raises(provider):
    """Bad token returns None."""
    assert provider.load_user_from_token("bogus-token") is None


def test_user_from_token_matches(provider):
    """Keith's token returns 'keith', not 'amy'."""
    token = provider.create_user_token(user_id="keith", client_id="test")
    user = provider.load_user_from_token(token)
    assert user == "keith"
    assert user != "amy"
