"""Tool integration tests with conversation-based schema and structured errors."""

import pytest

from ai_mailbox.tools.send import tool_send_message
from ai_mailbox.tools.inbox import tool_check_messages
from ai_mailbox.tools.reply import tool_reply_to_message
from ai_mailbox.tools.thread import tool_get_thread
from ai_mailbox.tools.identity import tool_whoami
from ai_mailbox.errors import is_error


# ---------------------------------------------------------------------------
# Scenario A: First Contact
# ---------------------------------------------------------------------------

class TestScenarioA:
    """First contact -- send, receive, auto-mark-read."""

    def test_keith_sends_to_amy(self, db):
        result = tool_send_message(db, user_id="keith", to="amy",
                                   body="Deploy question?",
                                   project="steertrue", subject="Deploy question")
        assert "message_id" in result
        assert result["from_user"] == "keith"
        assert result["to_user"] == "amy"

    def test_amy_sees_message_in_inbox(self, db):
        tool_send_message(db, user_id="keith", to="amy",
                          body="Deploy question?",
                          project="steertrue", subject="Deploy question")
        result = tool_check_messages(db, user_id="amy")
        assert result["message_count"] == 1
        msg = result["messages"][0]
        assert msg["project"] == "steertrue"
        assert msg["subject"] == "Deploy question"
        assert msg["body"] == "Deploy question?"

    def test_check_marks_as_read(self, db):
        tool_send_message(db, user_id="keith", to="amy", body="Read me")
        tool_check_messages(db, user_id="amy")
        result = tool_check_messages(db, user_id="amy", unread_only=True)
        assert result["message_count"] == 0


# ---------------------------------------------------------------------------
# Scenario B: Threaded Conversation
# ---------------------------------------------------------------------------

class TestScenarioB:
    """Threaded conversation -- 4-message back-and-forth."""

    def test_full_thread(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy",
                               body="Can you check the Railway logs?",
                               project="steertrue")
        r2 = tool_reply_to_message(db, user_id="amy",
                                   message_id=r1["message_id"],
                                   body="Logs show 502 errors since 3pm")
        r3 = tool_reply_to_message(db, user_id="keith",
                                   message_id=r2["message_id"],
                                   body="I'll redeploy, stand by")
        r4 = tool_reply_to_message(db, user_id="amy",
                                   message_id=r3["message_id"],
                                   body="Confirmed, it's back up")

        thread = tool_get_thread(db, user_id="keith",
                                 message_id=r1["message_id"])
        assert len(thread["messages"]) == 4
        bodies = [m["body"] for m in thread["messages"]]
        assert bodies[0] == "Can you check the Railway logs?"
        assert bodies[3] == "Confirmed, it's back up"

    def test_replies_inherit_project(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy",
                               body="Start", project="steertrue")
        r2 = tool_reply_to_message(db, user_id="amy",
                                   message_id=r1["message_id"],
                                   body="Reply")

        thread = tool_get_thread(db, user_id="keith",
                                 message_id=r1["message_id"])
        for msg in thread["messages"]:
            assert msg["project"] == "steertrue"

    def test_reply_to_chain_intact(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy", body="m1")
        r2 = tool_reply_to_message(db, user_id="amy",
                                   message_id=r1["message_id"], body="m2")
        r3 = tool_reply_to_message(db, user_id="keith",
                                   message_id=r2["message_id"], body="m3")

        thread = tool_get_thread(db, user_id="amy",
                                 message_id=r3["message_id"])
        assert len(thread["messages"]) == 3
        assert thread["messages"][1]["reply_to"] == r1["message_id"]
        assert thread["messages"][2]["reply_to"] == r2["message_id"]

    def test_any_participant_can_reply(self, db):
        """New behavior: both participants in a conversation can reply to any message."""
        r1 = tool_send_message(db, user_id="keith", to="amy", body="For Amy")
        # Keith (sender) replies to his own message -- this is now allowed
        r2 = tool_reply_to_message(db, user_id="keith",
                                   message_id=r1["message_id"],
                                   body="Follow-up from Keith")
        assert "message_id" in r2
        assert r2["from_user"] == "keith"


# ---------------------------------------------------------------------------
# Scenario C: Multi-Project Inbox Management
# ---------------------------------------------------------------------------

class TestScenarioC:
    """Multi-project inbox -- filtering and unread counts."""

    def _seed_messages(self, db):
        tool_send_message(db, user_id="keith", to="amy",
                          body="Dinner tonight?", project="general")
        tool_send_message(db, user_id="keith", to="amy",
                          body="PR #42 ready for review", project="steertrue")
        tool_send_message(db, user_id="keith", to="amy",
                          body="Did you call the florist?", project="wedding")

    def test_all_projects_inbox(self, db):
        self._seed_messages(db)
        result = tool_check_messages(db, user_id="amy", project=None)
        assert result["message_count"] == 3

    def test_filter_by_steertrue(self, db):
        self._seed_messages(db)
        result = tool_check_messages(db, user_id="amy", project="steertrue")
        assert result["message_count"] == 1

    def test_filter_by_general(self, db):
        self._seed_messages(db)
        result = tool_check_messages(db, user_id="amy", project="general")
        assert result["message_count"] == 1

    def test_whoami_unread_counts(self, db):
        self._seed_messages(db)
        result = tool_whoami(db, user_id="amy")
        assert result["user_id"] == "amy"
        assert result["unread_counts"]["general"] == 1
        assert result["unread_counts"]["steertrue"] == 1
        assert result["unread_counts"]["wedding"] == 1


# ---------------------------------------------------------------------------
# Scenario D: Thread Isolation
# ---------------------------------------------------------------------------

class TestScenarioD:
    """Thread isolation -- threads don't contaminate each other."""

    def test_threads_isolated(self, db):
        a1 = tool_send_message(db, user_id="keith", to="amy",
                               body="Bug in login", project="steertrue")
        b1 = tool_send_message(db, user_id="keith", to="amy",
                               body="Weekend plans?", project="general")

        tool_reply_to_message(db, user_id="amy",
                              message_id=a1["message_id"],
                              body="I see the issue")
        tool_reply_to_message(db, user_id="amy",
                              message_id=b1["message_id"],
                              body="Saturday works")

        thread_a = tool_get_thread(db, user_id="keith",
                                   message_id=a1["message_id"])
        thread_b = tool_get_thread(db, user_id="keith",
                                   message_id=b1["message_id"])

        assert len(thread_a["messages"]) == 2
        assert len(thread_b["messages"]) == 2
        assert all(m["project"] == "steertrue" for m in thread_a["messages"])
        assert all(m["project"] == "general" for m in thread_b["messages"])


# ---------------------------------------------------------------------------
# Scenario E: Error Handling (structured errors)
# ---------------------------------------------------------------------------

class TestScenarioE:
    """Error handling -- structured error responses."""

    def test_send_to_self_structured_error(self, db):
        result = tool_send_message(db, user_id="keith", to="keith", body="Self msg")
        assert is_error(result)
        assert result["error"]["code"] == "SELF_SEND"

    def test_send_to_nonexistent_user_structured_error(self, db):
        result = tool_send_message(db, user_id="keith", to="nobody", body="Hello")
        assert is_error(result)
        assert result["error"]["code"] == "RECIPIENT_NOT_FOUND"
        assert result["error"]["param"] == "to"

    def test_reply_to_nonexistent_message_structured_error(self, db):
        result = tool_reply_to_message(db, user_id="keith",
                                       message_id="fake-uuid", body="Reply")
        assert is_error(result)
        assert result["error"]["code"] == "MESSAGE_NOT_FOUND"

    def test_get_thread_invalid_id_structured_error(self, db):
        result = tool_get_thread(db, user_id="keith",
                                 message_id="nonexistent-uuid")
        assert is_error(result)
        assert result["error"]["code"] == "MESSAGE_NOT_FOUND"

    def test_check_empty_inbox(self, db):
        result = tool_check_messages(db, user_id="keith")
        assert result["message_count"] == 0
        assert result["messages"] == []

    def test_empty_body_structured_error(self, db):
        result = tool_send_message(db, user_id="keith", to="amy", body="")
        assert is_error(result)
        assert result["error"]["code"] == "EMPTY_BODY"
        assert result["error"]["param"] == "body"

    def test_empty_body_on_reply_structured_error(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy", body="hello")
        result = tool_reply_to_message(db, user_id="amy",
                                       message_id=r1["message_id"], body="  ")
        assert is_error(result)
        assert result["error"]["code"] == "EMPTY_BODY"

    def test_non_participant_get_thread_structured_error(self, db):
        """A non-participant cannot view a conversation thread."""
        db._conn.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("bob", "Bob", "test-bob-key"),
        )
        db._conn.commit()
        r1 = tool_send_message(db, user_id="keith", to="amy", body="private")
        result = tool_get_thread(db, user_id="bob",
                                 message_id=r1["message_id"])
        assert is_error(result)
        assert result["error"]["code"] == "PERMISSION_DENIED"

    def test_non_participant_reply_structured_error(self, db):
        """A non-participant cannot reply to a conversation."""
        db._conn.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("bob", "Bob", "test-bob-key"),
        )
        db._conn.commit()
        r1 = tool_send_message(db, user_id="keith", to="amy", body="private")
        result = tool_reply_to_message(db, user_id="bob",
                                       message_id=r1["message_id"],
                                       body="I shouldn't be here")
        assert is_error(result)
        assert result["error"]["code"] == "PERMISSION_DENIED"

    def test_all_errors_are_non_retryable(self, db):
        """Validation errors should not be retryable."""
        errors = [
            tool_send_message(db, user_id="keith", to="keith", body="self"),
            tool_send_message(db, user_id="keith", to="nobody", body="hello"),
            tool_send_message(db, user_id="keith", to="amy", body=""),
        ]
        for result in errors:
            assert is_error(result)
            assert result["error"]["retryable"] is False
