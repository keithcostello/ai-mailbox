"""Tests for create_group, add_participant, and list_users tools."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from ai_mailbox.db import queries
from ai_mailbox.errors import is_error
from ai_mailbox.tools.create_group import tool_create_group
from ai_mailbox.tools.add_participant import tool_add_participant
from ai_mailbox.tools.list_messages import tool_list_messages
from ai_mailbox.tools.list_users import tool_list_users
from ai_mailbox.tools.send import tool_send_message


# ---------------------------------------------------------------------------
# create_group
# ---------------------------------------------------------------------------

class TestCreateGroup:
    """create_group creates team_group conversations."""

    def test_creates_group(self, db, bob):
        result = tool_create_group(
            db, user_id="keith", name="Backend Team", members=["amy", bob],
        )
        assert not is_error(result)
        assert "conversation_id" in result
        assert result["name"] == "Backend Team"
        assert result["created"] is True
        assert set(result["participants"]) == {"keith", "amy", "bob"}

    def test_creator_included_as_participant(self, db, bob):
        result = tool_create_group(
            db, user_id="keith", name="Team", members=["amy"],
        )
        assert "keith" in result["participants"]

    def test_idempotent_same_name(self, db, bob):
        r1 = tool_create_group(
            db, user_id="keith", name="Backend", members=["amy", bob],
        )
        r2 = tool_create_group(
            db, user_id="keith", name="Backend", members=["amy", bob],
        )
        assert r1["conversation_id"] == r2["conversation_id"]
        assert r2["created"] is False

    def test_empty_name_error(self, db, bob):
        result = tool_create_group(
            db, user_id="keith", name="", members=["amy"],
        )
        assert is_error(result)
        assert result["error"]["code"] == "VALIDATION_ERROR"
        assert result["error"]["param"] == "name"

    def test_name_too_long_error(self, db):
        result = tool_create_group(
            db, user_id="keith", name="x" * 257, members=["amy"],
        )
        assert is_error(result)
        assert result["error"]["code"] == "VALIDATION_ERROR"

    def test_empty_members_error(self, db):
        result = tool_create_group(
            db, user_id="keith", name="Empty", members=[],
        )
        assert is_error(result)
        assert result["error"]["code"] == "VALIDATION_ERROR"
        assert result["error"]["param"] == "members"

    def test_nonexistent_member_error(self, db):
        result = tool_create_group(
            db, user_id="keith", name="Team", members=["nobody"],
        )
        assert is_error(result)
        assert result["error"]["code"] == "RECIPIENT_NOT_FOUND"

    def test_project_set(self, db, bob):
        result = tool_create_group(
            db, user_id="keith", name="Deploy Team",
            members=["amy", bob], project="deployment",
        )
        assert result["project"] == "deployment"


# ---------------------------------------------------------------------------
# add_participant
# ---------------------------------------------------------------------------

class TestAddParticipant:
    """add_participant adds users to group conversations."""

    def test_add_to_group(self, db, bob):
        r = tool_create_group(
            db, user_id="keith", name="Team", members=["amy"],
        )
        conv_id = r["conversation_id"]
        result = tool_add_participant(
            db, user_id="keith", conversation_id=conv_id, user_to_add=bob,
        )
        assert not is_error(result)
        assert result["user_added"] == "bob"
        assert result["already_member"] is False

    def test_idempotent_add(self, db, bob):
        r = tool_create_group(
            db, user_id="keith", name="Team", members=["amy", bob],
        )
        conv_id = r["conversation_id"]
        result = tool_add_participant(
            db, user_id="keith", conversation_id=conv_id, user_to_add=bob,
        )
        assert result["already_member"] is True

    def test_cannot_add_to_direct(self, db, bob):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        result = tool_add_participant(
            db, user_id="keith", conversation_id=conv_id, user_to_add=bob,
        )
        assert is_error(result)
        assert result["error"]["code"] == "VALIDATION_ERROR"

    def test_nonexistent_user_error(self, db):
        r = tool_create_group(
            db, user_id="keith", name="Team", members=["amy"],
        )
        result = tool_add_participant(
            db, user_id="keith", conversation_id=r["conversation_id"],
            user_to_add="nobody",
        )
        assert is_error(result)
        assert result["error"]["code"] == "RECIPIENT_NOT_FOUND"

    def test_permission_denied(self, db, bob):
        r = tool_create_group(
            db, user_id="keith", name="Team", members=["amy"],
        )
        result = tool_add_participant(
            db, user_id=bob, conversation_id=r["conversation_id"],
            user_to_add=bob,
        )
        assert is_error(result)
        assert result["error"]["code"] == "PERMISSION_DENIED"

    def test_conversation_not_found(self, db):
        result = tool_add_participant(
            db, user_id="keith", conversation_id="nonexistent",
            user_to_add="amy",
        )
        assert is_error(result)
        assert result["error"]["code"] == "CONVERSATION_NOT_FOUND"


# ---------------------------------------------------------------------------
# list_users
# ---------------------------------------------------------------------------

class TestListUsers:
    """list_users returns all users except the caller."""

    def test_excludes_caller(self, db):
        result = tool_list_users(db, user_id="keith")
        assert not is_error(result)
        ids = [u["id"] for u in result["users"]]
        assert "keith" not in ids
        assert "amy" in ids

    def test_count(self, db):
        result = tool_list_users(db, user_id="keith")
        assert result["count"] == 1  # only amy

    def test_calling_user_field(self, db):
        result = tool_list_users(db, user_id="keith")
        assert result["calling_user"] == "keith"

    def test_includes_display_name(self, db):
        result = tool_list_users(db, user_id="keith")
        amy = result["users"][0]
        assert "display_name" in amy


# ---------------------------------------------------------------------------
# list_users extended
# ---------------------------------------------------------------------------

class TestListUsersExtended:
    """Extended list_users coverage with multiple users."""

    def test_multiple_users_count(self, db, bob):
        result = tool_list_users(db, user_id="keith")
        assert result["count"] == 2  # amy + bob

    def test_user_type_field(self, db):
        result = tool_list_users(db, user_id="keith")
        for u in result["users"]:
            assert "user_type" in u

    def test_online_false_when_never_seen(self, db):
        result = tool_list_users(db, user_id="keith")
        for u in result["users"]:
            assert u["online"] is False

    def test_online_true_after_recent_activity(self, db):
        now = datetime.now(timezone.utc).isoformat()
        db._conn.execute(
            "UPDATE users SET last_seen = ? WHERE id = 'amy'", (now,),
        )
        db._conn.commit()
        result = tool_list_users(db, user_id="keith")
        amy = [u for u in result["users"] if u["id"] == "amy"][0]
        assert amy["online"] is True


# ---------------------------------------------------------------------------
# create_group extended
# ---------------------------------------------------------------------------

class TestCreateGroupExtended:
    """Extended create_group coverage."""

    def test_group_too_large(self, db, bob, charlie):
        with patch("ai_mailbox.tools.create_group.MAX_GROUP_SIZE", 3):
            result = tool_create_group(
                db, user_id="keith", name="Big",
                members=["amy", bob, charlie],
            )
            assert is_error(result)
            assert result["error"]["code"] == "GROUP_TOO_LARGE"

    def test_whitespace_name_error(self, db):
        result = tool_create_group(
            db, user_id="keith", name="   ", members=["amy"],
        )
        assert is_error(result)
        assert result["error"]["code"] == "VALIDATION_ERROR"

    def test_duplicate_members_deduplicated(self, db):
        result = tool_create_group(
            db, user_id="keith", name="Dedup Team",
            members=["amy", "amy"],
        )
        assert not is_error(result)
        assert set(result["participants"]) == {"keith", "amy"}


# ---------------------------------------------------------------------------
# add_participant extended
# ---------------------------------------------------------------------------

class TestAddParticipantExtended:
    """Extended add_participant coverage."""

    def test_group_too_large_on_add(self, db, bob, charlie):
        r = tool_create_group(
            db, user_id="keith", name="Small Team",
            members=["amy", bob],
        )
        with patch("ai_mailbox.tools.add_participant.MAX_GROUP_SIZE", 3):
            result = tool_add_participant(
                db, user_id="keith",
                conversation_id=r["conversation_id"],
                user_to_add=charlie,
            )
            assert is_error(result)
            assert result["error"]["code"] == "GROUP_TOO_LARGE"

    def test_added_user_sees_messages(self, db, bob, charlie):
        """After adding charlie, he can list messages in the group."""
        r = tool_create_group(
            db, user_id="keith", name="Team", members=["amy", bob],
        )
        conv_id = r["conversation_id"]
        # Send a message via group token flow
        r1 = tool_send_message(
            db, user_id="keith", body="team update",
            conversation_id=conv_id,
        )
        token = r1["group_send_token"]
        tool_send_message(
            db, user_id="keith", body="team update",
            conversation_id=conv_id,
            group_send_token=token,
        )
        # Add charlie
        tool_add_participant(
            db, user_id="keith", conversation_id=conv_id,
            user_to_add=charlie,
        )
        # Charlie can list messages
        result = tool_list_messages(
            db, user_id=charlie, conversation_id=conv_id,
        )
        assert not is_error(result)
        assert result["message_count"] >= 1
