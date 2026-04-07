"""Dead letter handling — messages sent to offline agents.

delivery_status column on messages:
  - 'delivered' (default): recipient was recently active
  - 'queued': recipient offline at send time (last_seen > threshold)

On next tool call from a previously-offline user, queued messages
transition to 'delivered' via process_dead_letters().
"""

from __future__ import annotations

import datetime
from datetime import timezone

import pytest

from ai_mailbox.config import DEAD_LETTER_THRESHOLD_HOURS


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestDeadLetterSchema:
    """delivery_status column exists and defaults correctly."""

    def test_delivery_status_column_exists(self, db):
        """Messages table has delivery_status column."""
        from ai_mailbox.db.queries import insert_message, find_or_create_direct_conversation
        conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
        result = insert_message(db, conv_id, "keith", "hello")
        msg = db.fetchone("SELECT delivery_status FROM messages WHERE id = ?", (result["id"],))
        assert msg is not None
        assert msg["delivery_status"] == "delivered"

    def test_delivery_status_default_is_delivered(self, db):
        """New messages default to 'delivered' status."""
        from ai_mailbox.db.queries import insert_message, find_or_create_direct_conversation
        conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
        result = insert_message(db, conv_id, "keith", "test")
        msg = db.fetchone("SELECT delivery_status FROM messages WHERE id = ?", (result["id"],))
        assert msg["delivery_status"] == "delivered"


# ---------------------------------------------------------------------------
# Offline detection
# ---------------------------------------------------------------------------

class TestOfflineDetection:
    """is_user_offline() checks last_seen against threshold."""

    def test_user_with_no_last_seen_is_offline(self, db):
        """A user who has never been seen is considered offline."""
        from ai_mailbox.db.queries import is_user_offline
        # Clear last_seen to simulate never-seen user
        db.execute("UPDATE users SET last_seen = NULL WHERE id = ?", ("keith",))
        db.commit()
        assert is_user_offline(db, "keith") is True

    def test_user_with_recent_last_seen_is_online(self, db):
        """A user seen recently is online."""
        from ai_mailbox.db.queries import is_user_offline, update_last_seen
        update_last_seen(db, "keith")
        assert is_user_offline(db, "keith") is False

    def test_user_with_stale_last_seen_is_offline(self, db):
        """A user whose last_seen exceeds the threshold is offline."""
        from ai_mailbox.db.queries import is_user_offline
        stale = datetime.datetime.now(timezone.utc) - datetime.timedelta(
            hours=DEAD_LETTER_THRESHOLD_HOURS + 1
        )
        db.execute(
            "UPDATE users SET last_seen = ? WHERE id = ?",
            (stale.isoformat(), "keith"),
        )
        db.commit()
        assert is_user_offline(db, "keith") is True

    def test_user_exactly_at_threshold_is_not_offline(self, db):
        """A user at exactly the threshold boundary is still online."""
        from ai_mailbox.db.queries import is_user_offline
        # Use 1 second inside the threshold to avoid timing edge cases
        boundary = datetime.datetime.now(timezone.utc) - datetime.timedelta(
            hours=DEAD_LETTER_THRESHOLD_HOURS, seconds=-1
        )
        db.execute(
            "UPDATE users SET last_seen = ? WHERE id = ?",
            (boundary.isoformat(), "keith"),
        )
        db.commit()
        assert is_user_offline(db, "keith") is False

    def test_nonexistent_user_is_offline(self, db):
        """A user that doesn't exist is considered offline."""
        from ai_mailbox.db.queries import is_user_offline
        assert is_user_offline(db, "nonexistent") is True


# ---------------------------------------------------------------------------
# Send to offline user
# ---------------------------------------------------------------------------

class TestSendToOfflineUser:
    """Sending a message to an offline user sets delivery_status='queued'."""

    def test_send_to_offline_user_queues_message(self, db):
        """Message to offline recipient gets queued delivery_status."""
        from ai_mailbox.tools.send import tool_send_message
        # Clear amy's last_seen to make her offline
        db.execute("UPDATE users SET last_seen = NULL WHERE id = ?", ("amy",))
        db.commit()
        result = tool_send_message(db, user_id="keith", to="amy", body="are you there?")
        assert "message_id" in result
        msg = db.fetchone("SELECT delivery_status FROM messages WHERE id = ?", (result["message_id"],))
        assert msg["delivery_status"] == "queued"

    def test_send_to_online_user_delivers(self, db):
        """Message to online recipient gets delivered status."""
        from ai_mailbox.db.queries import update_last_seen
        from ai_mailbox.tools.send import tool_send_message
        update_last_seen(db, "amy")
        result = tool_send_message(db, user_id="keith", to="amy", body="hello!")
        assert "message_id" in result
        msg = db.fetchone("SELECT delivery_status FROM messages WHERE id = ?", (result["message_id"],))
        assert msg["delivery_status"] == "delivered"

    def test_send_response_includes_delivery_status(self, db):
        """Tool response includes delivery_status field."""
        from ai_mailbox.tools.send import tool_send_message
        db.execute("UPDATE users SET last_seen = NULL WHERE id = ?", ("amy",))
        db.commit()
        result = tool_send_message(db, user_id="keith", to="amy", body="ping")
        assert "delivery_status" in result
        assert result["delivery_status"] == "queued"

    def test_send_to_online_user_response_shows_delivered(self, db):
        """Online recipient shows delivered in response."""
        from ai_mailbox.db.queries import update_last_seen
        from ai_mailbox.tools.send import tool_send_message
        update_last_seen(db, "amy")
        result = tool_send_message(db, user_id="keith", to="amy", body="hi")
        assert result["delivery_status"] == "delivered"


# ---------------------------------------------------------------------------
# Dead letter processing (redelivery on next activity)
# ---------------------------------------------------------------------------

class TestDeadLetterProcessing:
    """process_dead_letters() transitions queued -> delivered."""

    def test_process_dead_letters_transitions_queued_messages(self, db):
        """When a user comes back online, their queued messages become delivered."""
        from ai_mailbox.db.queries import (
            find_or_create_direct_conversation, insert_message, process_dead_letters,
        )
        conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
        result = insert_message(db, conv_id, "keith", "queued msg")
        db.execute("UPDATE messages SET delivery_status = 'queued' WHERE id = ?", (result["id"],))
        db.commit()

        count = process_dead_letters(db, "amy")
        assert count == 1

        msg = db.fetchone("SELECT delivery_status FROM messages WHERE id = ?", (result["id"],))
        assert msg["delivery_status"] == "delivered"

    def test_process_dead_letters_returns_zero_when_none_queued(self, db):
        """No queued messages means 0 processed."""
        from ai_mailbox.db.queries import process_dead_letters
        count = process_dead_letters(db, "keith")
        assert count == 0

    def test_process_dead_letters_only_affects_target_user(self, db, bob):
        """Only messages in conversations where the user is a participant are processed."""
        from ai_mailbox.db.queries import (
            find_or_create_direct_conversation, insert_message, process_dead_letters,
        )
        # Message to amy
        conv_amy = find_or_create_direct_conversation(db, "keith", "amy", "general")
        r1 = insert_message(db, conv_amy, "keith", "for amy")
        db.execute("UPDATE messages SET delivery_status = 'queued' WHERE id = ?", (r1["id"],))

        # Message to bob (different conversation)
        conv_bob = find_or_create_direct_conversation(db, "keith", bob, "general")
        r2 = insert_message(db, conv_bob, "keith", "for bob")
        db.execute("UPDATE messages SET delivery_status = 'queued' WHERE id = ?", (r2["id"],))
        db.commit()

        # Process amy's dead letters only
        count = process_dead_letters(db, "amy")
        assert count == 1

        # Bob's message still queued
        msg = db.fetchone("SELECT delivery_status FROM messages WHERE id = ?", (r2["id"],))
        assert msg["delivery_status"] == "queued"

    def test_process_dead_letters_does_not_touch_delivered(self, db):
        """Already-delivered messages are not affected."""
        from ai_mailbox.db.queries import (
            find_or_create_direct_conversation, insert_message, process_dead_letters,
        )
        conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
        insert_message(db, conv_id, "keith", "already delivered")

        count = process_dead_letters(db, "amy")
        assert count == 0


# ---------------------------------------------------------------------------
# Query: get_dead_letters
# ---------------------------------------------------------------------------

class TestGetDeadLetters:
    """get_dead_letters() returns queued messages for a user."""

    def test_get_dead_letters_returns_queued_messages(self, db):
        """Returns messages with delivery_status='queued' in user's conversations."""
        from ai_mailbox.db.queries import (
            find_or_create_direct_conversation, insert_message, get_dead_letters,
        )
        conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
        r1 = insert_message(db, conv_id, "keith", "queued 1")
        r2 = insert_message(db, conv_id, "keith", "queued 2")
        db.execute("UPDATE messages SET delivery_status = 'queued' WHERE id IN (?, ?)", (r1["id"], r2["id"]))
        db.commit()

        dead = get_dead_letters(db, "amy")
        assert len(dead) == 2
        assert all(d["delivery_status"] == "queued" for d in dead)

    def test_get_dead_letters_excludes_delivered(self, db):
        """Does not return delivered messages."""
        from ai_mailbox.db.queries import (
            find_or_create_direct_conversation, insert_message, get_dead_letters,
        )
        conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
        insert_message(db, conv_id, "keith", "delivered msg")

        dead = get_dead_letters(db, "amy")
        assert len(dead) == 0

    def test_get_dead_letters_empty_for_unknown_user(self, db):
        """Unknown user returns empty list."""
        from ai_mailbox.db.queries import get_dead_letters
        dead = get_dead_letters(db, "nonexistent")
        assert dead == []


# ---------------------------------------------------------------------------
# Integration with update_last_seen
# ---------------------------------------------------------------------------

class TestDeadLetterAutoProcessing:
    """update_last_seen_and_process_dead_letters triggers dead letter processing."""

    def test_update_last_seen_processes_dead_letters(self, db):
        """When update_last_seen fires, queued messages transition to delivered."""
        from ai_mailbox.db.queries import (
            find_or_create_direct_conversation, insert_message,
            update_last_seen_and_process_dead_letters,
        )
        conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
        r1 = insert_message(db, conv_id, "keith", "queued msg")
        db.execute("UPDATE messages SET delivery_status = 'queued' WHERE id = ?", (r1["id"],))
        db.commit()

        count = update_last_seen_and_process_dead_letters(db, "amy")
        assert count == 1

        msg = db.fetchone("SELECT delivery_status FROM messages WHERE id = ?", (r1["id"],))
        assert msg["delivery_status"] == "delivered"

    def test_update_last_seen_returns_zero_when_no_dead_letters(self, db):
        """No dead letters means 0."""
        from ai_mailbox.db.queries import update_last_seen_and_process_dead_letters
        count = update_last_seen_and_process_dead_letters(db, "keith")
        assert count == 0
