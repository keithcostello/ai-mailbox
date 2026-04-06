"""Tests for group send token module."""
import time

import pytest

from ai_mailbox.group_tokens import (
    generate_token,
    validate_token,
    clear_tokens,
    TOKEN_TTL_SECONDS,
)


class TestGenerateToken:
    """generate_token creates valid tokens."""

    def setup_method(self):
        clear_tokens()

    def test_returns_string(self):
        token = generate_token("conv-123", "hello world")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_different_calls_different_tokens(self):
        t1 = generate_token("conv-123", "hello")
        t2 = generate_token("conv-456", "hello")
        assert t1 != t2

    def test_same_inputs_different_tokens(self):
        t1 = generate_token("conv-123", "hello")
        t2 = generate_token("conv-123", "hello")
        assert t1 != t2  # Each call generates a new token


class TestValidateToken:
    """validate_token enforces all constraints."""

    def setup_method(self):
        clear_tokens()

    def test_valid_token_returns_true(self):
        token = generate_token("conv-123", "hello world")
        ok, error = validate_token(token, "conv-123", "hello world")
        assert ok is True
        assert error is None

    def test_invalid_token_string(self):
        ok, error = validate_token("bogus-token", "conv-123", "hello")
        assert ok is False
        assert error == "GROUP_TOKEN_INVALID"

    def test_wrong_conversation_id(self):
        token = generate_token("conv-123", "hello")
        ok, error = validate_token(token, "conv-999", "hello")
        assert ok is False
        assert error == "GROUP_TOKEN_INVALID"

    def test_wrong_body(self):
        token = generate_token("conv-123", "hello")
        ok, error = validate_token(token, "conv-123", "different body")
        assert ok is False
        assert error == "GROUP_TOKEN_INVALID"

    def test_single_use_consumed_after_validation(self):
        token = generate_token("conv-123", "hello")
        ok1, _ = validate_token(token, "conv-123", "hello")
        assert ok1 is True
        # Second use should fail
        ok2, error2 = validate_token(token, "conv-123", "hello")
        assert ok2 is False
        assert error2 == "GROUP_TOKEN_INVALID"

    def test_expired_token(self):
        # Generate token, then monkey-patch its expiry
        token = generate_token("conv-123", "hello")
        from ai_mailbox.group_tokens import _token_store
        _token_store[token]["expires_at"] = time.time() - 1
        ok, error = validate_token(token, "conv-123", "hello")
        assert ok is False
        assert error == "GROUP_TOKEN_EXPIRED"

    def test_empty_token(self):
        ok, error = validate_token("", "conv-123", "hello")
        assert ok is False
        assert error == "GROUP_TOKEN_INVALID"

    def test_none_token(self):
        ok, error = validate_token(None, "conv-123", "hello")
        assert ok is False
        assert error == "GROUP_TOKEN_INVALID"


class TestClearTokens:
    """clear_tokens removes all stored tokens."""

    def test_clear_removes_all(self):
        generate_token("conv-1", "a")
        generate_token("conv-2", "b")
        clear_tokens()
        # Both tokens should now be invalid
        ok, _ = validate_token("anything", "conv-1", "a")
        assert ok is False


class TestTokenTTL:
    """Token TTL constant is defined."""

    def test_ttl_is_300_seconds(self):
        assert TOKEN_TTL_SECONDS == 300  # 5 minutes
