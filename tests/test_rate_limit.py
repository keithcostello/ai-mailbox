"""Tests for rate limiting module."""
import time

import pytest

from ai_mailbox.rate_limit import (
    check_rate_limit,
    MCP_READ_LIMIT,
    MCP_WRITE_LIMIT,
    MCP_GROUP_LIMIT,
    WEB_LOGIN_LIMIT,
    WEB_PAGE_LIMIT,
    reset_storage,
)


class TestRateLimitDefinitions:
    """Rate limit constants are defined correctly."""

    def test_mcp_read_limit_exists(self):
        assert MCP_READ_LIMIT is not None

    def test_mcp_write_limit_exists(self):
        assert MCP_WRITE_LIMIT is not None

    def test_mcp_group_limit_exists(self):
        assert MCP_GROUP_LIMIT is not None

    def test_web_login_limit_exists(self):
        assert WEB_LOGIN_LIMIT is not None

    def test_web_page_limit_exists(self):
        assert WEB_PAGE_LIMIT is not None


class TestCheckRateLimit:
    """check_rate_limit enforces limits correctly."""

    def setup_method(self):
        reset_storage()

    def test_within_limit_returns_true(self):
        assert check_rate_limit(MCP_READ_LIMIT, "user", "keith") is True

    def test_exceeding_limit_returns_false(self):
        # MCP_READ_LIMIT is 60/minute -- hit it 60 times, 61st should fail
        for _ in range(60):
            check_rate_limit(MCP_READ_LIMIT, "user", "keith")
        assert check_rate_limit(MCP_READ_LIMIT, "user", "keith") is False

    def test_different_users_isolated(self):
        # Exhaust keith's limit
        for _ in range(60):
            check_rate_limit(MCP_READ_LIMIT, "user", "keith")
        # amy should still be within limit
        assert check_rate_limit(MCP_READ_LIMIT, "user", "amy") is True

    def test_write_limit_lower_than_read(self):
        # MCP_WRITE_LIMIT is 30/minute
        for _ in range(30):
            check_rate_limit(MCP_WRITE_LIMIT, "user", "keith")
        assert check_rate_limit(MCP_WRITE_LIMIT, "user", "keith") is False

    def test_group_limit_lower_than_write(self):
        # MCP_GROUP_LIMIT is 10/minute
        for _ in range(10):
            check_rate_limit(MCP_GROUP_LIMIT, "user", "keith")
        assert check_rate_limit(MCP_GROUP_LIMIT, "user", "keith") is False

    def test_login_limit(self):
        # WEB_LOGIN_LIMIT is 5/minute
        for _ in range(5):
            check_rate_limit(WEB_LOGIN_LIMIT, "ip", "192.168.1.1")
        assert check_rate_limit(WEB_LOGIN_LIMIT, "ip", "192.168.1.1") is False

    def test_different_limit_types_independent(self):
        # Exhaust write limit for keith
        for _ in range(30):
            check_rate_limit(MCP_WRITE_LIMIT, "user", "keith")
        # Read limit should still work for keith
        assert check_rate_limit(MCP_READ_LIMIT, "user", "keith") is True

    def test_reset_storage_clears_limits(self):
        for _ in range(60):
            check_rate_limit(MCP_READ_LIMIT, "user", "keith")
        assert check_rate_limit(MCP_READ_LIMIT, "user", "keith") is False
        reset_storage()
        assert check_rate_limit(MCP_READ_LIMIT, "user", "keith") is True
