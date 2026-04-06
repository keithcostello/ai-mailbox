"""Tests for the archive_conversation MCP tool -- archive, unarchive, auto-unarchive, inbox filtering."""

import pytest

from ai_mailbox.db.queries import (
    find_or_create_direct_conversation,
    get_inbox,
    insert_message,
)
from ai_mailbox.errors import is_error
from ai_mailbox.tools.archive import tool_archive_conversation


@pytest.fixture
def conversation_with_messages(db):
    """Create a conversation between keith and amy with two messages."""
    conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
    insert_message(db, conv_id, "keith", "Hello Amy")
    insert_message(db, conv_id, "amy", "Hello Keith")
    return conv_id


class TestArchiveBasic:
    """Basic archive and unarchive operations."""

    def test_archive_conversation(self, db, conversation_with_messages):
        conv_id = conversation_with_messages
        result = tool_archive_conversation(db, user_id="keith", conversation_id=conv_id)
        assert not is_error(result)
        assert result["archived"] is True
        assert result["conversation_id"] == conv_id
        assert result["archived_at"] is not None

    def test_unarchive_conversation(self, db, conversation_with_messages):
        conv_id = conversation_with_messages
        tool_archive_conversation(db, user_id="keith", conversation_id=conv_id)
        result = tool_archive_conversation(db, user_id="keith", conversation_id=conv_id, archive=False)
        assert not is_error(result)
        assert result["archived"] is False
        assert result["archived_at"] is None

    def test_archive_is_idempotent(self, db, conversation_with_messages):
        conv_id = conversation_with_messages
        r1 = tool_archive_conversation(db, user_id="keith", conversation_id=conv_id)
        r2 = tool_archive_conversation(db, user_id="keith", conversation_id=conv_id)
        assert not is_error(r2)
        assert r2["archived"] is True

    def test_unarchive_non_archived_is_idempotent(self, db, conversation_with_messages):
        conv_id = conversation_with_messages
        result = tool_archive_conversation(db, user_id="keith", conversation_id=conv_id, archive=False)
        assert not is_error(result)
        assert result["archived"] is False


class TestArchiveValidation:
    """Validation errors for archive operations."""

    def test_conversation_not_found(self, db):
        result = tool_archive_conversation(db, user_id="keith", conversation_id="nonexistent")
        assert is_error(result)
        assert result["error"]["code"] == "CONVERSATION_NOT_FOUND"

    def test_not_a_participant(self, db, conversation_with_messages):
        db.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("bob", "Bob", "bob-key"),
        )
        db.commit()
        conv_id = conversation_with_messages
        result = tool_archive_conversation(db, user_id="bob", conversation_id=conv_id)
        assert is_error(result)
        assert result["error"]["code"] == "PERMISSION_DENIED"


class TestArchivePerUser:
    """Archive is per-user, not per-conversation."""

    def test_archive_only_affects_archiving_user(self, db, conversation_with_messages):
        conv_id = conversation_with_messages
        tool_archive_conversation(db, user_id="keith", conversation_id=conv_id)

        # Keith's inbox should exclude the archived conversation
        keith_inbox = get_inbox(db, "keith")
        keith_conv_ids = [c["conversation_id"] for c in keith_inbox]
        assert conv_id not in keith_conv_ids

        # Amy's inbox should still have it
        amy_inbox = get_inbox(db, "amy")
        amy_conv_ids = [c["conversation_id"] for c in amy_inbox]
        assert conv_id in amy_conv_ids


class TestArchiveInboxFiltering:
    """Inbox filtering respects archive state."""

    def test_archived_excluded_from_inbox_by_default(self, db, conversation_with_messages):
        conv_id = conversation_with_messages
        tool_archive_conversation(db, user_id="keith", conversation_id=conv_id)
        inbox = get_inbox(db, "keith")
        conv_ids = [c["conversation_id"] for c in inbox]
        assert conv_id not in conv_ids

    def test_include_archived_shows_archived(self, db, conversation_with_messages):
        conv_id = conversation_with_messages
        tool_archive_conversation(db, user_id="keith", conversation_id=conv_id)
        inbox = get_inbox(db, "keith", include_archived=True)
        conv_ids = [c["conversation_id"] for c in inbox]
        assert conv_id in conv_ids

    def test_archived_flag_in_inbox_entry(self, db, conversation_with_messages):
        conv_id = conversation_with_messages
        tool_archive_conversation(db, user_id="keith", conversation_id=conv_id)
        inbox = get_inbox(db, "keith", include_archived=True)
        entry = next(c for c in inbox if c["conversation_id"] == conv_id)
        assert entry["archived"] is True

    def test_non_archived_has_archived_false(self, db, conversation_with_messages):
        inbox = get_inbox(db, "keith")
        for entry in inbox:
            assert entry["archived"] is False


class TestAutoUnarchive:
    """New messages auto-unarchive for recipients."""

    def test_new_message_unarchives_for_recipient(self, db, conversation_with_messages):
        conv_id = conversation_with_messages
        tool_archive_conversation(db, user_id="amy", conversation_id=conv_id)

        # Keith sends a new message
        insert_message(db, conv_id, "keith", "New message!")

        # Amy's archive should be cleared
        inbox = get_inbox(db, "amy")
        conv_ids = [c["conversation_id"] for c in inbox]
        assert conv_id in conv_ids

    def test_sender_archive_preserved_on_send(self, db, conversation_with_messages):
        conv_id = conversation_with_messages
        tool_archive_conversation(db, user_id="keith", conversation_id=conv_id)

        # Keith sends a message -- their own archive state should remain
        insert_message(db, conv_id, "keith", "Sending while archived")

        inbox = get_inbox(db, "keith")
        conv_ids = [c["conversation_id"] for c in inbox]
        assert conv_id not in conv_ids

    def test_auto_unarchive_only_affects_archived_participants(self, db, conversation_with_messages):
        conv_id = conversation_with_messages
        # Only amy archives
        tool_archive_conversation(db, user_id="amy", conversation_id=conv_id)

        # Keith sends -- amy should be unarchived, keith was never archived
        insert_message(db, conv_id, "keith", "Update")

        amy_inbox = get_inbox(db, "amy")
        assert any(c["conversation_id"] == conv_id for c in amy_inbox)
