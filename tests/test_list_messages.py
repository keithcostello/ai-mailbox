"""Tests for list_messages and mark_read tools."""
import pytest

from ai_mailbox.db import queries
from ai_mailbox.errors import is_error
from ai_mailbox.tools.list_messages import tool_list_messages
from ai_mailbox.tools.mark_read import tool_mark_read


class TestListMessagesBasic:
    """list_messages returns messages without side effects."""

    def test_returns_messages(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "hello")
        result = tool_list_messages(db, user_id="keith")
        assert result["user"] == "keith"
        assert result["message_count"] == 1

    def test_no_side_effect_on_read_cursor(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "hello")
        # Call twice -- same result (cursor not advanced)
        r1 = tool_list_messages(db, user_id="keith")
        r2 = tool_list_messages(db, user_id="keith")
        assert r1["message_count"] == r2["message_count"] == 1

    def test_unread_only_default(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "old")
        queries.advance_read_cursor(db, conv_id, "keith", 1)
        queries.insert_message(db, conv_id, "amy", "new")
        result = tool_list_messages(db, user_id="keith")
        assert result["message_count"] == 1
        assert result["messages"][0]["body"] == "new"

    def test_unread_only_false(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "old")
        queries.advance_read_cursor(db, conv_id, "keith", 1)
        queries.insert_message(db, conv_id, "amy", "new")
        result = tool_list_messages(db, user_id="keith", unread_only=False)
        assert result["message_count"] == 2

    def test_empty_inbox(self, db):
        result = tool_list_messages(db, user_id="keith")
        assert result["message_count"] == 0
        assert result["messages"] == []


class TestListMessagesFilters:
    """list_messages supports project and conversation filters."""

    def test_project_filter(self, db):
        conv1 = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        conv2 = queries.find_or_create_direct_conversation(db, "keith", "amy", "alerts")
        queries.insert_message(db, conv1, "amy", "general msg")
        queries.insert_message(db, conv2, "amy", "alert msg")
        result = tool_list_messages(db, user_id="keith", project="alerts")
        assert result["message_count"] == 1
        assert result["messages"][0]["body"] == "alert msg"

    def test_conversation_id_filter(self, db):
        conv1 = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        conv2 = queries.find_or_create_direct_conversation(db, "keith", "amy", "alerts")
        queries.insert_message(db, conv1, "amy", "general msg")
        queries.insert_message(db, conv2, "amy", "alert msg")
        result = tool_list_messages(db, user_id="keith", conversation_id=conv1)
        assert result["message_count"] == 1
        assert result["messages"][0]["body"] == "general msg"

    def test_conversation_permission_denied(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "keith", "secret")
        # bob doesn't exist as participant -- simulate by adding a user
        db._conn.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("bob", "Bob", "test-bob-key"),
        )
        db._conn.commit()
        result = tool_list_messages(db, user_id="bob", conversation_id=conv_id)
        assert is_error(result)
        assert result["error"]["code"] == "PERMISSION_DENIED"


class TestListMessagesPagination:
    """list_messages supports cursor pagination."""

    def test_limit(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        for i in range(5):
            queries.insert_message(db, conv_id, "amy", f"msg {i}")
        result = tool_list_messages(db, user_id="keith", limit=3)
        assert result["message_count"] == 3
        assert result["has_more"] is True
        assert result["next_cursor"] is not None

    def test_after_sequence_with_conversation_id(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        for i in range(5):
            queries.insert_message(db, conv_id, "amy", f"msg {i}")
        result = tool_list_messages(
            db, user_id="keith", conversation_id=conv_id, after_sequence=3
        )
        assert result["message_count"] == 2

    def test_invalid_limit(self, db):
        result = tool_list_messages(db, user_id="keith", limit=0)
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_PARAMETER"

    def test_limit_too_high_clamped(self, db):
        result = tool_list_messages(db, user_id="keith", limit=300)
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_PARAMETER"


class TestMarkReadBasic:
    """mark_read advances the read cursor."""

    def test_advances_to_max(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "msg 1")
        queries.insert_message(db, conv_id, "amy", "msg 2")
        queries.insert_message(db, conv_id, "amy", "msg 3")
        result = tool_mark_read(db, user_id="keith", conversation_id=conv_id)
        assert result["marked_up_to"] == 3
        assert result["previous_cursor"] == 0

    def test_advances_to_specific_sequence(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "msg 1")
        queries.insert_message(db, conv_id, "amy", "msg 2")
        queries.insert_message(db, conv_id, "amy", "msg 3")
        result = tool_mark_read(db, user_id="keith", conversation_id=conv_id, up_to_sequence=2)
        assert result["marked_up_to"] == 2

    def test_clamps_to_max_sequence(self, db):
        """Cursor is clamped to actual max, not the requested value."""
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "msg 1")
        queries.insert_message(db, conv_id, "amy", "msg 2")
        result = tool_mark_read(db, user_id="keith", conversation_id=conv_id, up_to_sequence=999)
        assert result["marked_up_to"] == 2  # clamped to max

    def test_cursor_never_goes_backward(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "msg 1")
        queries.insert_message(db, conv_id, "amy", "msg 2")
        queries.insert_message(db, conv_id, "amy", "msg 3")
        tool_mark_read(db, user_id="keith", conversation_id=conv_id, up_to_sequence=3)
        result = tool_mark_read(db, user_id="keith", conversation_id=conv_id, up_to_sequence=1)
        assert result["marked_up_to"] == 3  # didn't go backward

    def test_permission_denied(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        db._conn.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("bob", "Bob", "test-bob-key"),
        )
        db._conn.commit()
        result = tool_mark_read(db, user_id="bob", conversation_id=conv_id)
        assert is_error(result)
        assert result["error"]["code"] == "PERMISSION_DENIED"

    def test_conversation_not_found(self, db):
        result = tool_mark_read(db, user_id="keith", conversation_id="nonexistent")
        assert is_error(result)
        assert result["error"]["code"] == "CONVERSATION_NOT_FOUND"

    def test_mark_read_then_list_shows_fewer_unread(self, db):
        """Integration: mark_read + list_messages work together."""
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "msg 1")
        queries.insert_message(db, conv_id, "amy", "msg 2")
        queries.insert_message(db, conv_id, "amy", "msg 3")

        r1 = tool_list_messages(db, user_id="keith")
        assert r1["message_count"] == 3

        tool_mark_read(db, user_id="keith", conversation_id=conv_id, up_to_sequence=2)

        r2 = tool_list_messages(db, user_id="keith")
        assert r2["message_count"] == 1
        assert r2["messages"][0]["body"] == "msg 3"
