"""Full coverage tests for mailbox_send_message tool."""

from unittest.mock import patch

import pytest

from ai_mailbox.db.queries import find_or_create_direct_conversation, get_message
from ai_mailbox.errors import is_error
from ai_mailbox.tools.send import tool_send_message


class TestSendValidation:
    """Edge-case validation for send_message."""

    def test_whitespace_only_body(self, db):
        result = tool_send_message(db, user_id="keith", to="amy", body="   \t\n")
        assert is_error(result)
        assert result["error"]["code"] == "EMPTY_BODY"

    def test_self_only_in_list(self, db):
        result = tool_send_message(db, user_id="keith", to=["keith"], body="solo")
        assert is_error(result)
        assert result["error"]["code"] == "MISSING_PARAMETER"

    def test_self_in_list_becomes_direct(self, db):
        """Sender is silently removed from recipient list; single remaining = direct."""
        result = tool_send_message(
            db, user_id="keith", to=["keith", "amy"], body="hi",
        )
        assert not is_error(result)
        assert result["to_user"] == "amy"
        # No confirmation_required -- it's a direct send
        assert "confirmation_required" not in result


class TestSendConversationMode:
    """Send to existing conversation by ID."""

    def test_conversation_not_found(self, db):
        result = tool_send_message(
            db, user_id="keith", body="hello",
            conversation_id="nonexistent-conv-id",
        )
        assert is_error(result)
        assert result["error"]["code"] == "CONVERSATION_NOT_FOUND"

    def test_non_participant_permission_denied(self, db, bob):
        conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
        result = tool_send_message(
            db, user_id=bob, body="intruder",
            conversation_id=conv_id,
        )
        assert is_error(result)
        assert result["error"]["code"] == "PERMISSION_DENIED"


class TestSendGroupEdgeCases:
    """Group send edge cases."""

    def test_group_too_large(self, db, bob, charlie):
        with patch("ai_mailbox.config.MAX_GROUP_SIZE", 3):
            result = tool_send_message(
                db, user_id="keith",
                to=["amy", bob, charlie],
                body="too many",
            )
            assert is_error(result)
            assert result["error"]["code"] == "GROUP_TOO_LARGE"

    def test_group_token_consumed_single_use(self, db, bob):
        """Token can only be used once."""
        r1 = tool_send_message(
            db, user_id="keith", to=["amy", bob], body="group msg",
        )
        token = r1["group_send_token"]
        # First use succeeds
        r2 = tool_send_message(
            db, user_id="keith", to=["amy", bob], body="group msg",
            group_send_token=token,
        )
        assert not is_error(r2)
        assert "message_id" in r2
        # Second use fails
        r3 = tool_send_message(
            db, user_id="keith", to=["amy", bob], body="group msg",
            group_send_token=token,
        )
        assert is_error(r3)


class TestSendResponseShape:
    """Verify response fields and metadata."""

    def test_subject_roundtrips(self, db):
        result = tool_send_message(
            db, user_id="keith", to="amy", body="hi",
            subject="Important",
        )
        msg = get_message(db, result["message_id"])
        assert msg["subject"] == "Important"

    def test_long_body_includes_display_note(self, db):
        body = "x" * 3000
        result = tool_send_message(db, user_id="keith", to="amy", body=body)
        assert not is_error(result)
        assert "body_display_note" in result
        assert "2000" in result["body_display_note"]

    def test_short_body_no_display_note(self, db):
        result = tool_send_message(db, user_id="keith", to="amy", body="short")
        assert not is_error(result)
        assert "body_display_note" not in result
