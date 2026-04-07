"""System messages — reserved 'system' sender for platform-generated messages.

The 'system' user is a reserved account (user_type='system') that generates
automated messages like join notifications, delivery failures, etc.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# System user exists
# ---------------------------------------------------------------------------

class TestSystemUser:
    """The 'system' user is seeded by migration."""

    def test_system_user_exists(self, db):
        """system user exists in the database."""
        from ai_mailbox.db.queries import get_user
        user = get_user(db, "system")
        assert user is not None

    def test_system_user_type_is_system(self, db):
        """system user has user_type='system'."""
        from ai_mailbox.db.queries import get_user
        user = get_user(db, "system")
        assert user["user_type"] == "system"

    def test_system_user_not_in_list_users(self, db):
        """system user is excluded from list_users results."""
        from ai_mailbox.db.queries import get_all_users
        users = get_all_users(db)
        user_ids = [u["id"] for u in users]
        assert "system" not in user_ids

    def test_cannot_send_as_system_via_tool(self, db):
        """The send_message tool rejects from_user='system'."""
        from ai_mailbox.tools.send import tool_send_message
        result = tool_send_message(db, user_id="system", to="keith", body="hi")
        assert "error" in result
        assert result["error"]["code"] == "SYSTEM_USER_DENIED"


# ---------------------------------------------------------------------------
# insert_system_message
# ---------------------------------------------------------------------------

class TestInsertSystemMessage:
    """insert_system_message() creates messages from the 'system' user."""

    def test_insert_system_message_basic(self, db):
        """System message inserts into a conversation."""
        from ai_mailbox.db.queries import (
            find_or_create_direct_conversation, insert_system_message, get_message,
        )
        conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
        result = insert_system_message(db, conv_id, "keith joined the conversation")
        assert "id" in result
        assert "sequence_number" in result

        msg = get_message(db, result["id"])
        assert msg["from_user"] == "system"
        assert msg["body"] == "keith joined the conversation"
        assert msg["content_type"] == "text/plain"

    def test_system_message_gets_sequence_number(self, db):
        """System messages get proper sequence numbers in the conversation."""
        from ai_mailbox.db.queries import (
            find_or_create_direct_conversation, insert_message, insert_system_message,
        )
        conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
        insert_message(db, conv_id, "keith", "user msg")  # seq 1
        result = insert_system_message(db, conv_id, "system event")  # seq 2
        assert result["sequence_number"] == 2

    def test_system_message_appears_in_thread(self, db):
        """System messages appear when fetching conversation thread."""
        from ai_mailbox.db.queries import (
            find_or_create_direct_conversation, insert_message,
            insert_system_message, get_conversation_messages,
        )
        conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
        insert_message(db, conv_id, "keith", "hello")
        insert_system_message(db, conv_id, "amy joined")
        insert_message(db, conv_id, "amy", "hi back")

        msgs, _ = get_conversation_messages(db, conv_id)
        assert len(msgs) == 3
        assert msgs[0]["from_user"] == "keith"
        assert msgs[1]["from_user"] == "system"
        assert msgs[2]["from_user"] == "amy"

    def test_system_message_with_content_type(self, db):
        """System messages support custom content_type."""
        from ai_mailbox.db.queries import (
            find_or_create_direct_conversation, insert_system_message, get_message,
        )
        conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
        result = insert_system_message(
            db, conv_id, '{"event": "join"}', content_type="application/json"
        )
        msg = get_message(db, result["id"])
        assert msg["content_type"] == "application/json"


# ---------------------------------------------------------------------------
# System messages on group events
# ---------------------------------------------------------------------------

class TestSystemMessagesOnEvents:
    """Automatic system messages on group actions."""

    def test_add_participant_creates_system_message(self, db, bob):
        """Adding a participant to a group generates a system message."""
        from ai_mailbox.db.queries import (
            create_team_group, get_conversation_messages,
        )
        from ai_mailbox.tools.add_participant import tool_add_participant
        conv_id = create_team_group(db, "test-group", "keith", ["amy"])

        result = tool_add_participant(db, user_id="keith", conversation_id=conv_id, user_to_add=bob)
        assert "error" not in result

        msgs, _ = get_conversation_messages(db, conv_id)
        system_msgs = [m for m in msgs if m["from_user"] == "system"]
        assert len(system_msgs) == 1
        assert "bob" in system_msgs[0]["body"]

    def test_dead_letter_creates_system_message(self, db):
        """Sending to an offline user generates a system message about queued delivery."""
        from ai_mailbox.tools.send import tool_send_message
        # Clear amy's last_seen to make her offline
        db.execute("UPDATE users SET last_seen = NULL WHERE id = ?", ("amy",))
        db.commit()
        result = tool_send_message(db, user_id="keith", to="amy", body="hello offline")
        assert result.get("delivery_status") == "queued"

        from ai_mailbox.db.queries import get_conversation_messages
        msgs, _ = get_conversation_messages(db, result["conversation_id"])
        system_msgs = [m for m in msgs if m["from_user"] == "system"]
        assert len(system_msgs) == 1
        assert "offline" in system_msgs[0]["body"].lower() or "queued" in system_msgs[0]["body"].lower()


# ---------------------------------------------------------------------------
# list_users excludes system
# ---------------------------------------------------------------------------

class TestListUsersExcludesSystem:
    """The list_users tool should not show the system user."""

    def test_list_users_tool_excludes_system(self, db):
        """list_users tool response does not include system user."""
        from ai_mailbox.tools.list_users import tool_list_users
        result = tool_list_users(db, user_id="keith")
        user_ids = [u["id"] for u in result.get("users", [])]
        assert "system" not in user_ids
