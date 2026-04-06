"""Full coverage tests for mailbox_reply_to_message tool."""

import pytest

from ai_mailbox.db.queries import get_message
from ai_mailbox.errors import is_error
from ai_mailbox.tools.create_group import tool_create_group
from ai_mailbox.tools.send import tool_send_message
from ai_mailbox.tools.reply import tool_reply_to_message


class TestReplyEdgeCases:
    """Reply edge cases not covered by test_tools.py."""

    def test_reply_inherits_subject(self, db):
        r1 = tool_send_message(
            db, user_id="keith", to="amy", body="hello",
            subject="Deploy Plan",
        )
        r2 = tool_reply_to_message(
            db, user_id="amy", message_id=r1["message_id"],
            body="ack",
        )
        msg = get_message(db, r2["message_id"])
        assert msg["subject"] == "Deploy Plan"

    def test_reply_in_group_conversation(self, db, bob):
        group = tool_create_group(
            db, user_id="keith", name="Team", members=["amy", bob],
        )
        # Send via group token
        r1 = tool_send_message(
            db, user_id="keith", body="group question",
            conversation_id=group["conversation_id"],
        )
        token = r1["group_send_token"]
        r1_sent = tool_send_message(
            db, user_id="keith", body="group question",
            conversation_id=group["conversation_id"],
            group_send_token=token,
        )
        # Bob replies
        r2 = tool_reply_to_message(
            db, user_id=bob, message_id=r1_sent["message_id"],
            body="bob's answer",
        )
        assert not is_error(r2)
        assert r2["from_user"] == "bob"

    def test_whitespace_body(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy", body="hello")
        result = tool_reply_to_message(
            db, user_id="amy", message_id=r1["message_id"],
            body="   ",
        )
        assert is_error(result)
        assert result["error"]["code"] == "EMPTY_BODY"

    def test_reply_content_type_default(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy", body="hello")
        r2 = tool_reply_to_message(
            db, user_id="amy", message_id=r1["message_id"],
            body="reply",
        )
        msg = get_message(db, r2["message_id"])
        assert msg["content_type"] == "text/plain"


class TestReplyResponseShape:
    """Verify all expected fields in reply response."""

    def test_response_has_all_fields(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy", body="hello")
        r2 = tool_reply_to_message(
            db, user_id="amy", message_id=r1["message_id"],
            body="reply",
        )
        assert "message_id" in r2
        assert "conversation_id" in r2
        assert r2["from_user"] == "amy"
        assert r2["to_user"] == "keith"
        assert "project" in r2

    def test_long_body_includes_display_note(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy", body="hello")
        r2 = tool_reply_to_message(
            db, user_id="amy", message_id=r1["message_id"],
            body="x" * 3000,
        )
        assert not is_error(r2)
        assert "body_display_note" in r2
        assert "2000" in r2["body_display_note"]
