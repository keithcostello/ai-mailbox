"""list_group_participants tool -- returns authoritative participant list for a conversation."""

from __future__ import annotations

import pytest


class TestListParticipantsBasic:
    """Core functionality of list_group_participants."""

    def test_returns_participants_for_group(self, db):
        """Returns participant list for a group the caller belongs to."""
        from ai_mailbox.db.queries import create_team_group
        from ai_mailbox.tools.list_participants import tool_list_participants
        conv_id = create_team_group(db, "test-group", "keith", ["amy"])
        result = tool_list_participants(db, user_id="keith", conversation_id=conv_id)
        assert "participants" in result
        ids = [p["user_id"] for p in result["participants"]]
        assert "keith" in ids
        assert "amy" in ids
        assert result["conversation_id"] == conv_id
        assert result["participant_count"] == 2

    def test_returns_participants_for_direct(self, db):
        """Works for direct conversations too."""
        from ai_mailbox.db.queries import find_or_create_direct_conversation
        from ai_mailbox.tools.list_participants import tool_list_participants
        conv_id = find_or_create_direct_conversation(db, "keith", "amy", "general")
        result = tool_list_participants(db, user_id="keith", conversation_id=conv_id)
        ids = [p["user_id"] for p in result["participants"]]
        assert sorted(ids) == ["amy", "keith"]
        assert result["type"] == "direct"

    def test_includes_conversation_metadata(self, db):
        """Response includes conversation type, name, project."""
        from ai_mailbox.db.queries import create_team_group
        from ai_mailbox.tools.list_participants import tool_list_participants
        conv_id = create_team_group(db, "my-group", "keith", ["amy"], project="general")
        result = tool_list_participants(db, user_id="keith", conversation_id=conv_id)
        assert result["type"] == "team_group"
        assert result["name"] == "my-group"
        assert result["project"] == "general"


class TestListParticipantsPermissions:
    """Permission checks for list_group_participants."""

    def test_rejects_non_participant(self, db, bob):
        """Non-participant cannot list members."""
        from ai_mailbox.db.queries import create_team_group
        from ai_mailbox.tools.list_participants import tool_list_participants
        conv_id = create_team_group(db, "private-group", "keith", ["amy"])
        result = tool_list_participants(db, user_id=bob, conversation_id=conv_id)
        assert "error" in result
        assert result["error"]["code"] == "PERMISSION_DENIED"

    def test_rejects_nonexistent_conversation(self, db):
        """Nonexistent conversation returns error."""
        from ai_mailbox.tools.list_participants import tool_list_participants
        result = tool_list_participants(db, user_id="keith", conversation_id="fake-id")
        assert "error" in result
        assert result["error"]["code"] == "CONVERSATION_NOT_FOUND"


class TestListParticipantsAfterChanges:
    """Participant list reflects mutations."""

    def test_reflects_added_participant(self, db, bob):
        """After add_participant, list shows new member."""
        from ai_mailbox.db.queries import create_team_group, add_participant
        from ai_mailbox.tools.list_participants import tool_list_participants
        conv_id = create_team_group(db, "grow-group", "keith", ["amy"])
        add_participant(db, conv_id, bob)
        result = tool_list_participants(db, user_id="keith", conversation_id=conv_id)
        ids = [p["user_id"] for p in result["participants"]]
        assert bob in ids
        assert result["participant_count"] == 3

    def test_includes_user_metadata(self, db):
        """Each participant has display_name and user_type."""
        from ai_mailbox.db.queries import create_team_group
        from ai_mailbox.tools.list_participants import tool_list_participants
        conv_id = create_team_group(db, "meta-group", "keith", ["amy"])
        result = tool_list_participants(db, user_id="keith", conversation_id=conv_id)
        for p in result["participants"]:
            assert "user_id" in p
            assert "display_name" in p
            assert "user_type" in p

    def test_excludes_system_user_from_participants(self, db):
        """System user is not listed as a participant even if in the table."""
        from ai_mailbox.db.queries import create_team_group, add_participant
        from ai_mailbox.tools.list_participants import tool_list_participants
        conv_id = create_team_group(db, "sys-group", "keith", ["amy"])
        # Force-add system as participant (shouldn't happen, but guard it)
        add_participant(db, conv_id, "system")
        result = tool_list_participants(db, user_id="keith", conversation_id=conv_id)
        ids = [p["user_id"] for p in result["participants"]]
        assert "system" not in ids
