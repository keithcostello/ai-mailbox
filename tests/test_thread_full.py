"""Full coverage tests for mailbox_get_thread tool."""

import pytest

from ai_mailbox.errors import is_error
from ai_mailbox.tools.send import tool_send_message
from ai_mailbox.tools.reply import tool_reply_to_message
from ai_mailbox.tools.thread import tool_get_thread


class TestGetThreadPagination:
    """Pagination and limit behavior."""

    def _seed_thread(self, db, count=10):
        """Send count messages in a single conversation, return first message_id."""
        r1 = tool_send_message(db, user_id="keith", to="amy", body="msg-1")
        for i in range(2, count + 1):
            sender = "keith" if i % 2 == 1 else "amy"
            tool_reply_to_message(
                db, user_id=sender, message_id=r1["message_id"],
                body=f"msg-{i}",
            )
        return r1["message_id"]

    def test_default_limit_is_5(self, db):
        msg_id = self._seed_thread(db, 10)
        result = tool_get_thread(db, user_id="keith", message_id=msg_id)
        assert result["message_count"] == 5
        assert result["has_more"] is True

    def test_limit_respected(self, db):
        msg_id = self._seed_thread(db, 10)
        result = tool_get_thread(db, user_id="keith", message_id=msg_id, limit=2)
        assert result["message_count"] == 2
        assert result["has_more"] is True

    def test_after_sequence_pagination(self, db):
        msg_id = self._seed_thread(db, 10)
        result = tool_get_thread(
            db, user_id="keith", message_id=msg_id,
            after_sequence=2, limit=3,
        )
        assert result["messages"][0]["sequence_number"] == 3
        assert result["message_count"] == 3

    def test_next_cursor_when_has_more(self, db):
        msg_id = self._seed_thread(db, 10)
        result = tool_get_thread(db, user_id="keith", message_id=msg_id, limit=3)
        assert result["next_cursor"] == result["messages"][-1]["sequence_number"]

    def test_next_cursor_none_when_complete(self, db):
        msg_id = self._seed_thread(db, 3)
        result = tool_get_thread(db, user_id="keith", message_id=msg_id, limit=10)
        assert result["has_more"] is False
        assert result["next_cursor"] is None

    def test_limit_zero_error(self, db):
        msg_id = self._seed_thread(db, 1)
        result = tool_get_thread(db, user_id="keith", message_id=msg_id, limit=0)
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_PARAMETER"

    def test_limit_over_200_error(self, db):
        msg_id = self._seed_thread(db, 1)
        result = tool_get_thread(db, user_id="keith", message_id=msg_id, limit=201)
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_PARAMETER"


class TestGetThreadSummary:
    """Summary field for earlier messages."""

    def _seed_thread(self, db, count=10):
        r1 = tool_send_message(db, user_id="keith", to="amy", body="msg-1")
        for i in range(2, count + 1):
            sender = "keith" if i % 2 == 1 else "amy"
            tool_reply_to_message(
                db, user_id=sender, message_id=r1["message_id"],
                body=f"msg-{i}",
            )
        return r1["message_id"]

    def test_summary_when_earlier_messages(self, db):
        msg_id = self._seed_thread(db, 10)
        result = tool_get_thread(db, user_id="keith", message_id=msg_id)
        assert "summary" in result
        assert "earlier messages" in result["summary"]
        assert "keith" in result["summary"]
        assert "amy" in result["summary"]

    def test_no_summary_when_all_shown(self, db):
        msg_id = self._seed_thread(db, 3)
        result = tool_get_thread(db, user_id="keith", message_id=msg_id, limit=10)
        assert "summary" not in result


class TestGetThreadSingleMessage:
    """Single-message thread behavior."""

    def test_single_message_thread(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy", body="only message")
        result = tool_get_thread(db, user_id="keith", message_id=r1["message_id"])
        assert result["message_count"] == 1
        assert result["has_more"] is False

    def test_root_message_id_matches(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy", body="only message")
        result = tool_get_thread(db, user_id="keith", message_id=r1["message_id"])
        assert result["root_message_id"] == r1["message_id"]


class TestGetThreadResponseShape:
    """Verify response structure and metadata."""

    def test_conversation_metadata(self, db):
        r1 = tool_send_message(
            db, user_id="keith", to="amy", body="hello",
            project="steertrue",
        )
        result = tool_get_thread(db, user_id="keith", message_id=r1["message_id"])
        conv = result["conversation"]
        assert "id" in conv
        assert conv["type"] == "direct"
        assert conv["project"] == "steertrue"
        assert set(conv["participants"]) == {"keith", "amy"}

    def test_message_count_matches_length(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy", body="hello")
        tool_reply_to_message(
            db, user_id="amy", message_id=r1["message_id"], body="reply",
        )
        result = tool_get_thread(db, user_id="keith", message_id=r1["message_id"])
        assert result["message_count"] == len(result["messages"])


class TestGetThreadBodyTruncation:
    """Body truncation at 2000 char display limit."""

    def test_long_body_truncated(self, db):
        body = "x" * 5000
        r1 = tool_send_message(db, user_id="keith", to="amy", body=body)
        result = tool_get_thread(db, user_id="keith", message_id=r1["message_id"])
        msg = result["messages"][0]
        assert len(msg["body"]) == 2003  # 2000 + "..."
        assert msg["body"].endswith("...")
        assert msg["truncated"] is True

    def test_short_body_not_truncated(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy", body="short")
        result = tool_get_thread(db, user_id="keith", message_id=r1["message_id"])
        msg = result["messages"][0]
        assert msg["body"] == "short"
        assert msg["truncated"] is False

    def test_truncated_has_full_length(self, db):
        body = "y" * 5000
        r1 = tool_send_message(db, user_id="keith", to="amy", body=body)
        result = tool_get_thread(db, user_id="keith", message_id=r1["message_id"])
        msg = result["messages"][0]
        assert msg["full_length"] == 5000
