"""Tool integration tests with conversation-based schema and structured errors."""

import pytest

from ai_mailbox.tools.send import tool_send_message
from ai_mailbox.tools.reply import tool_reply_to_message
from ai_mailbox.tools.thread import tool_get_thread
from ai_mailbox.tools.identity import tool_whoami
from ai_mailbox.tools.list_messages import tool_list_messages
from ai_mailbox.tools.mark_read import tool_mark_read
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
        result = tool_list_messages(db, user_id="amy")
        assert result["message_count"] == 1
        msg = result["messages"][0]
        assert msg["subject"] == "Deploy question"
        assert msg["body"] == "Deploy question?"

    def test_mark_read_clears_unread(self, db):
        r = tool_send_message(db, user_id="keith", to="amy", body="Read me")
        result = tool_list_messages(db, user_id="amy")
        assert result["message_count"] == 1
        tool_mark_read(db, user_id="amy", conversation_id=r["conversation_id"])
        result = tool_list_messages(db, user_id="amy", unread_only=True)
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
        result = tool_list_messages(db, user_id="amy", project=None)
        assert result["message_count"] == 3

    def test_filter_by_steertrue(self, db):
        self._seed_messages(db)
        result = tool_list_messages(db, user_id="amy", project="steertrue")
        assert result["message_count"] == 1

    def test_filter_by_general(self, db):
        self._seed_messages(db)
        result = tool_list_messages(db, user_id="amy", project="general")
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

    def test_list_empty_inbox(self, db):
        result = tool_list_messages(db, user_id="keith")
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


# ---------------------------------------------------------------------------
# Sprint 2: Enhanced send_message
# ---------------------------------------------------------------------------

class TestSendMessageEnhanced:
    """Sprint 2 enhancements to send_message."""

    def test_body_too_long(self, db):
        result = tool_send_message(db, user_id="keith", to="amy", body="x" * 10_001)
        assert is_error(result)
        assert result["error"]["code"] == "BODY_TOO_LONG"
        assert result["error"]["param"] == "body"

    def test_body_at_limit_succeeds(self, db):
        result = tool_send_message(db, user_id="keith", to="amy", body="x" * 10_000)
        assert not is_error(result)
        assert "message_id" in result

    def test_content_type_stored(self, db):
        result = tool_send_message(
            db, user_id="keith", to="amy", body='{"data": "test"}',
            content_type="application/json",
        )
        assert not is_error(result)
        from ai_mailbox.db.queries import get_message
        msg = get_message(db, result["message_id"])
        assert msg["content_type"] == "application/json"

    def test_idempotency_key_prevents_duplicate(self, db):
        r1 = tool_send_message(
            db, user_id="keith", to="amy", body="hello",
            idempotency_key="key-1",
        )
        assert not is_error(r1)
        r2 = tool_send_message(
            db, user_id="keith", to="amy", body="hello",
            idempotency_key="key-1",
        )
        assert is_error(r2)
        assert r2["error"]["code"] == "DUPLICATE_MESSAGE"

    def test_to_array_returns_confirmation_required(self, db):
        """Sending to a group without token returns confirmation payload."""
        db._conn.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("bob", "Bob", "test-bob-key"),
        )
        db._conn.commit()
        result = tool_send_message(
            db, user_id="keith", to=["amy", "bob"], body="group msg",
        )
        # Should return confirmation payload (not error, not success)
        assert "confirmation_required" in result
        assert result["confirmation_required"] is True
        assert "group_send_token" in result

    def test_to_array_with_valid_token_sends(self, db):
        """Sending to a group with valid token succeeds."""
        db._conn.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("bob", "Bob", "test-bob-key"),
        )
        db._conn.commit()
        # First call: get token
        r1 = tool_send_message(
            db, user_id="keith", to=["amy", "bob"], body="group msg",
        )
        token = r1["group_send_token"]
        # Second call: send with token
        r2 = tool_send_message(
            db, user_id="keith", to=["amy", "bob"], body="group msg",
            group_send_token=token,
        )
        assert not is_error(r2)
        assert "message_id" in r2
        assert set(r2["to_users"]) == {"amy", "bob"}

    def test_to_single_element_list_is_direct(self, db):
        result = tool_send_message(db, user_id="keith", to=["amy"], body="direct")
        assert not is_error(result)
        assert result["to_user"] == "amy"

    def test_conversation_id_direct_no_token_needed(self, db):
        """Sending to existing direct conversation via conversation_id works without token."""
        from ai_mailbox.db.queries import find_or_create_direct_conversation
        conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
        result = tool_send_message(
            db, user_id="keith", body="via conv_id",
            conversation_id=conv_id,
        )
        assert not is_error(result)
        assert "message_id" in result

    def test_conversation_id_group_requires_token(self, db):
        """Sending to group conversation via conversation_id requires token."""
        db._conn.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("bob", "Bob", "test-bob-key"),
        )
        db._conn.commit()
        from ai_mailbox.db.queries import find_or_create_group_by_members
        conv_id, _ = find_or_create_group_by_members(db, "keith", ["amy", "bob"], "general")
        result = tool_send_message(
            db, user_id="keith", body="group via conv_id",
            conversation_id=conv_id,
        )
        assert "confirmation_required" in result

    def test_missing_to_and_conversation_id(self, db):
        result = tool_send_message(db, user_id="keith", body="hello")
        assert is_error(result)
        assert result["error"]["code"] == "MISSING_PARAMETER"

    def test_response_includes_to_users_list(self, db):
        result = tool_send_message(db, user_id="keith", to="amy", body="hi")
        assert result["to_users"] == ["amy"]

    def test_content_type_json_valid_body(self, db):
        """Sending application/json with valid JSON body succeeds."""
        result = tool_send_message(
            db, user_id="keith", to="amy",
            body='{"key": "value"}', content_type="application/json",
        )
        assert not is_error(result)
        assert "message_id" in result

    def test_content_type_json_invalid_body(self, db):
        """Sending application/json with non-JSON body returns INVALID_JSON."""
        result = tool_send_message(
            db, user_id="keith", to="amy",
            body="not json", content_type="application/json",
        )
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_JSON"
        assert result["error"]["param"] == "body"
        assert result["error"]["retryable"] is False

    def test_content_type_plaintext_no_json_check(self, db):
        """text/plain body is not validated as JSON."""
        result = tool_send_message(
            db, user_id="keith", to="amy",
            body="just plain text", content_type="text/plain",
        )
        assert not is_error(result)

    def test_to_array_deduplicates(self, db):
        """Duplicate recipients are silently removed."""
        db._conn.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("bob", "Bob", "test-bob-key"),
        )
        db._conn.commit()
        result = tool_send_message(
            db, user_id="keith", to=["amy", "amy", "bob"], body="dedup test",
        )
        assert "confirmation_required" in result
        assert len(result["group"]["participants"]) == 3  # keith, amy, bob


# ---------------------------------------------------------------------------
# Sprint 2: Enhanced reply_to_message
# ---------------------------------------------------------------------------

class TestReplyEnhanced:
    """Sprint 2 enhancements to reply_to_message."""

    def test_body_too_long(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy", body="hello")
        result = tool_reply_to_message(
            db, user_id="amy", message_id=r1["message_id"],
            body="x" * 10_001,
        )
        assert is_error(result)
        assert result["error"]["code"] == "BODY_TOO_LONG"

    def test_content_type_on_reply(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy", body="hello")
        result = tool_reply_to_message(
            db, user_id="amy", message_id=r1["message_id"],
            body='{"status": "ok"}', content_type="application/json",
        )
        assert not is_error(result)
        from ai_mailbox.db.queries import get_message
        msg = get_message(db, result["message_id"])
        assert msg["content_type"] == "application/json"

    def test_idempotency_key_on_reply(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy", body="hello")
        result = tool_reply_to_message(
            db, user_id="amy", message_id=r1["message_id"],
            body="reply", idempotency_key="reply-key-1",
        )
        assert not is_error(result)
        # Duplicate should fail
        dup = tool_reply_to_message(
            db, user_id="amy", message_id=r1["message_id"],
            body="reply", idempotency_key="reply-key-1",
        )
        assert is_error(dup)
        assert dup["error"]["code"] == "DUPLICATE_MESSAGE"

    def test_response_includes_conversation_id(self, db):
        r1 = tool_send_message(db, user_id="keith", to="amy", body="hello")
        result = tool_reply_to_message(
            db, user_id="amy", message_id=r1["message_id"], body="reply",
        )
        assert "conversation_id" in result

    def test_reply_json_valid(self, db):
        """Reply with application/json and valid JSON body succeeds."""
        r1 = tool_send_message(db, user_id="keith", to="amy", body="hello")
        result = tool_reply_to_message(
            db, user_id="amy", message_id=r1["message_id"],
            body='{"status": "ok"}', content_type="application/json",
        )
        assert not is_error(result)

    def test_reply_json_invalid(self, db):
        """Reply with application/json and non-JSON body returns INVALID_JSON."""
        r1 = tool_send_message(db, user_id="keith", to="amy", body="hello")
        result = tool_reply_to_message(
            db, user_id="amy", message_id=r1["message_id"],
            body="not json at all", content_type="application/json",
        )
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_JSON"
        assert result["error"]["param"] == "body"
        assert result["error"]["retryable"] is False
