"""Test Suite 3: Real Communication Scenarios A-E (OAuth — no api_key)."""

import pytest

from ai_mailbox.tools.send import tool_send_message
from ai_mailbox.tools.inbox import tool_check_messages
from ai_mailbox.tools.reply import tool_reply_to_message
from ai_mailbox.tools.thread import tool_get_thread
from ai_mailbox.tools.identity import tool_whoami


# ---------------------------------------------------------------------------
# Scenario A: First Contact
# ---------------------------------------------------------------------------

class TestScenarioA:
    """First contact — send, receive, auto-mark-read."""

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
    """Threaded conversation — 4-message back-and-forth."""

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


# ---------------------------------------------------------------------------
# Scenario C: Multi-Project Inbox Management
# ---------------------------------------------------------------------------

class TestScenarioC:
    """Multi-project inbox — filtering and unread counts."""

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
    """Thread isolation — threads don't contaminate each other."""

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
# Scenario E: Edge Cases
# ---------------------------------------------------------------------------

class TestScenarioE:
    """Edge cases — error handling."""

    def test_send_to_self_errors(self, db):
        result = tool_send_message(db, user_id="keith", to="keith",
                                   body="Self msg")
        assert "error" in result

    def test_send_to_nonexistent_user_errors(self, db):
        result = tool_send_message(db, user_id="keith", to="nobody",
                                   body="Hello")
        assert "error" in result

    def test_reply_to_nonexistent_message_errors(self, db):
        result = tool_reply_to_message(db, user_id="keith",
                                       message_id="fake-uuid", body="Reply")
        assert "error" in result

    def test_reply_to_message_not_addressed_to_you_errors(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy",
                               body="For Amy")
        result = tool_reply_to_message(db, user_id="keith",
                                       message_id=r1["message_id"],
                                       body="Self-reply")
        assert "error" in result

    def test_get_thread_invalid_id_errors(self, db):
        result = tool_get_thread(db, user_id="keith",
                                 message_id="nonexistent-uuid")
        assert "error" in result

    def test_check_empty_inbox(self, db):
        result = tool_check_messages(db, user_id="keith")
        assert result["message_count"] == 0
        assert result["messages"] == []

    def test_empty_body_errors(self, db):
        result = tool_send_message(db, user_id="keith", to="amy", body="")
        assert "error" in result
