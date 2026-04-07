"""Full coverage tests for mailbox_whoami tool."""

import pytest

from ai_mailbox.errors import is_error
from ai_mailbox.tools.identity import tool_whoami
from ai_mailbox.tools.send import tool_send_message
from ai_mailbox.tools.mark_read import tool_mark_read


class TestWhoamiBasic:
    """Basic whoami response fields."""

    def test_returns_user_id(self, db):
        result = tool_whoami(db, user_id="keith")
        assert result["user_id"] == "keith"

    def test_returns_display_name(self, db):
        result = tool_whoami(db, user_id="keith")
        assert result["display_name"] == "Keith"

    def test_returns_user_type(self, db):
        result = tool_whoami(db, user_id="keith")
        assert result["user_type"] == "human"

    def test_returns_session_mode(self, db):
        result = tool_whoami(db, user_id="keith")
        assert result["session_mode"] == "persistent"

    def test_returns_last_seen_none(self, db):
        # Clear last_seen to test the None case
        db._conn.execute("UPDATE users SET last_seen = NULL WHERE id = 'keith'")
        db._conn.commit()
        result = tool_whoami(db, user_id="keith")
        assert result["last_seen"] is None

    def test_other_users_excludes_self(self, db):
        result = tool_whoami(db, user_id="keith")
        ids = [u["id"] for u in result["other_users"]]
        assert "keith" not in ids

    def test_other_users_have_required_fields(self, db):
        result = tool_whoami(db, user_id="keith")
        for u in result["other_users"]:
            assert "id" in u
            assert "display_name" in u

    def test_user_not_found(self, db):
        result = tool_whoami(db, user_id="ghost")
        assert is_error(result)
        assert result["error"]["code"] == "RECIPIENT_NOT_FOUND"


class TestWhoamiMultipleUsers:
    """Whoami with more than 2 users."""

    def test_other_users_count_with_three(self, db, bob):
        result = tool_whoami(db, user_id="keith")
        assert len(result["other_users"]) == 2

    def test_other_users_count_with_four(self, db, bob, charlie):
        result = tool_whoami(db, user_id="keith")
        assert len(result["other_users"]) == 3


class TestWhoamiUnreadCounts:
    """Unread count behavior."""

    def test_unread_empty_no_messages(self, db):
        result = tool_whoami(db, user_id="keith")
        assert result["unread_counts"] == {}

    def test_sender_has_unread_own_messages(self, db):
        """Sender's read cursor is not auto-advanced; own messages count as unread."""
        tool_send_message(db, user_id="keith", to="amy", body="hello")
        result = tool_whoami(db, user_id="keith")
        # Keith sent the message but his read cursor is still 0 — message is unread
        assert result["unread_counts"]["general"] == 1

    def test_unread_decreases_after_mark_read(self, db):
        r = tool_send_message(db, user_id="keith", to="amy", body="read me")
        result_before = tool_whoami(db, user_id="amy")
        assert result_before["unread_counts"]["general"] == 1
        tool_mark_read(db, user_id="amy", conversation_id=r["conversation_id"])
        result_after = tool_whoami(db, user_id="amy")
        assert result_after["unread_counts"].get("general", 0) == 0
