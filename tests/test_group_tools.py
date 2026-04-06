"""Tests for create_group, add_participant, and list_users tools."""
import pytest

from ai_mailbox.db import queries
from ai_mailbox.errors import is_error
from ai_mailbox.tools.create_group import tool_create_group
from ai_mailbox.tools.add_participant import tool_add_participant
from ai_mailbox.tools.list_users import tool_list_users


@pytest.fixture
def bob(db):
    db._conn.execute(
        "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
        ("bob", "Bob", "test-bob-key"),
    )
    db._conn.commit()
    return "bob"


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
