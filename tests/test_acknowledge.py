"""Tests for the acknowledge MCP tool -- state transitions, permissions, validation."""

import pytest

from ai_mailbox.db.queries import (
    find_or_create_direct_conversation,
    insert_message,
    get_message,
)
from ai_mailbox.errors import is_error
from ai_mailbox.tools.acknowledge import tool_acknowledge


@pytest.fixture
def conversation_with_message(db):
    """Create a conversation between keith and amy with one message from keith."""
    conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
    result = insert_message(db, conv_id, "keith", "Hello Amy")
    msg_id = result["id"]
    return conv_id, msg_id


class TestAcknowledgeValidation:
    """Validate inputs before any state change."""

    def test_invalid_state_value(self, db, conversation_with_message):
        conv_id, msg_id = conversation_with_message
        result = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="bogus")
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_PARAMETER"

    def test_message_not_found(self, db):
        result = tool_acknowledge(db, user_id="amy", message_id="nonexistent", state="received")
        assert is_error(result)
        assert result["error"]["code"] == "MESSAGE_NOT_FOUND"

    def test_not_a_participant(self, db, conversation_with_message):
        """A user not in the conversation cannot ACK."""
        db.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("bob", "Bob", "bob-key"),
        )
        db.commit()
        _, msg_id = conversation_with_message
        result = tool_acknowledge(db, user_id="bob", message_id=msg_id, state="received")
        assert is_error(result)
        assert result["error"]["code"] == "PERMISSION_DENIED"

    def test_cannot_ack_own_message(self, db, conversation_with_message):
        """The sender cannot acknowledge their own message."""
        _, msg_id = conversation_with_message
        result = tool_acknowledge(db, user_id="keith", message_id=msg_id, state="received")
        assert is_error(result)
        assert result["error"]["code"] == "PERMISSION_DENIED"
        assert "own message" in result["error"]["message"].lower()


class TestAcknowledgeTransitions:
    """Forward-only state machine enforcement."""

    def test_pending_to_received(self, db, conversation_with_message):
        _, msg_id = conversation_with_message
        result = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="received")
        assert not is_error(result)
        assert result["ack_state"] == "received"
        assert result["previous_state"] == "pending"
        assert result["message_id"] == msg_id
        assert result["acknowledged_by"] == "amy"

    def test_pending_to_processing(self, db, conversation_with_message):
        _, msg_id = conversation_with_message
        result = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="processing")
        assert not is_error(result)
        assert result["ack_state"] == "processing"

    def test_pending_to_completed(self, db, conversation_with_message):
        _, msg_id = conversation_with_message
        result = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="completed")
        assert not is_error(result)
        assert result["ack_state"] == "completed"

    def test_pending_to_failed(self, db, conversation_with_message):
        _, msg_id = conversation_with_message
        result = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="failed")
        assert not is_error(result)
        assert result["ack_state"] == "failed"

    def test_received_to_processing(self, db, conversation_with_message):
        _, msg_id = conversation_with_message
        tool_acknowledge(db, user_id="amy", message_id=msg_id, state="received")
        result = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="processing")
        assert not is_error(result)
        assert result["ack_state"] == "processing"
        assert result["previous_state"] == "received"

    def test_received_to_completed(self, db, conversation_with_message):
        _, msg_id = conversation_with_message
        tool_acknowledge(db, user_id="amy", message_id=msg_id, state="received")
        result = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="completed")
        assert not is_error(result)
        assert result["ack_state"] == "completed"

    def test_received_to_failed(self, db, conversation_with_message):
        _, msg_id = conversation_with_message
        tool_acknowledge(db, user_id="amy", message_id=msg_id, state="received")
        result = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="failed")
        assert not is_error(result)
        assert result["ack_state"] == "failed"

    def test_processing_to_completed(self, db, conversation_with_message):
        _, msg_id = conversation_with_message
        tool_acknowledge(db, user_id="amy", message_id=msg_id, state="processing")
        result = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="completed")
        assert not is_error(result)
        assert result["ack_state"] == "completed"

    def test_processing_to_failed(self, db, conversation_with_message):
        _, msg_id = conversation_with_message
        tool_acknowledge(db, user_id="amy", message_id=msg_id, state="processing")
        result = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="failed")
        assert not is_error(result)
        assert result["ack_state"] == "failed"


class TestAcknowledgeTerminalStates:
    """Terminal states (completed, failed) reject further transitions."""

    def test_completed_is_terminal(self, db, conversation_with_message):
        _, msg_id = conversation_with_message
        tool_acknowledge(db, user_id="amy", message_id=msg_id, state="completed")
        result = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="processing")
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_STATE_TRANSITION"
        assert result["error"]["retryable"] is False

    def test_failed_is_terminal(self, db, conversation_with_message):
        _, msg_id = conversation_with_message
        tool_acknowledge(db, user_id="amy", message_id=msg_id, state="failed")
        result = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="completed")
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_STATE_TRANSITION"

    def test_cannot_go_backward(self, db, conversation_with_message):
        """completed -> received is invalid."""
        _, msg_id = conversation_with_message
        tool_acknowledge(db, user_id="amy", message_id=msg_id, state="completed")
        result = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="received")
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_STATE_TRANSITION"

    def test_processing_to_received_invalid(self, db, conversation_with_message):
        """processing -> received is backward, invalid."""
        _, msg_id = conversation_with_message
        tool_acknowledge(db, user_id="amy", message_id=msg_id, state="processing")
        result = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="received")
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_STATE_TRANSITION"


class TestAcknowledgeDBPersistence:
    """Verify ACK state is persisted to the database."""

    def test_ack_persists_to_db(self, db, conversation_with_message):
        _, msg_id = conversation_with_message
        tool_acknowledge(db, user_id="amy", message_id=msg_id, state="received")
        msg = get_message(db, msg_id)
        assert msg["ack_state"] == "received"

    def test_response_includes_conversation_id(self, db, conversation_with_message):
        conv_id, msg_id = conversation_with_message
        result = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="received")
        assert result["conversation_id"] == conv_id


class TestAcknowledgeGroupConversation:
    """ACK behavior in group conversations."""

    def test_non_sender_participant_can_ack(self, db):
        """In a 3-person group, any non-sender can ACK."""
        db.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("bob", "Bob", "bob-key"),
        )
        db.commit()
        from ai_mailbox.db.queries import create_team_group
        conv_id = create_team_group(db, "team", "keith", ["amy", "bob"])
        result = insert_message(db, conv_id, "keith", "Hello team")
        msg_id = result["id"]

        # amy can ACK
        r1 = tool_acknowledge(db, user_id="amy", message_id=msg_id, state="received")
        assert not is_error(r1)
        assert r1["ack_state"] == "received"

        # bob can also ACK (last-writer-wins)
        r2 = tool_acknowledge(db, user_id="bob", message_id=msg_id, state="processing")
        assert not is_error(r2)
        assert r2["ack_state"] == "processing"
        assert r2["previous_state"] == "received"
