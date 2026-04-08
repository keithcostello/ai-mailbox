"""Profile metadata: query functions and update_profile tool."""

from __future__ import annotations

import json

import pytest

from ai_mailbox.config import MAX_PROFILE_METADATA_SIZE, MAX_EXPERTISE_TAGS


# ---------------------------------------------------------------------------
# Query layer
# ---------------------------------------------------------------------------

class TestGetProfileMetadata:
    """get_user_profile_metadata returns parsed JSON."""

    def test_empty_default(self, db):
        from ai_mailbox.db.queries import get_user_profile_metadata
        meta = get_user_profile_metadata(db, "keith")
        assert meta == {}

    def test_returns_stored_data(self, db):
        from ai_mailbox.db.queries import get_user_profile_metadata, update_user_profile_metadata
        update_user_profile_metadata(db, "keith", {"team": "eng", "expertise_tags": ["python"]})
        meta = get_user_profile_metadata(db, "keith")
        assert meta["team"] == "eng"
        assert meta["expertise_tags"] == ["python"]

    def test_nonexistent_user_returns_empty(self, db):
        from ai_mailbox.db.queries import get_user_profile_metadata
        meta = get_user_profile_metadata(db, "nonexistent")
        assert meta == {}

    def test_invalid_json_returns_empty(self, db):
        from ai_mailbox.db.queries import get_user_profile_metadata
        db.execute("UPDATE users SET profile_metadata = 'not json' WHERE id = ?", ("keith",))
        db.commit()
        meta = get_user_profile_metadata(db, "keith")
        assert meta == {}


class TestUpdateProfileMetadata:
    """update_user_profile_metadata writes JSON."""

    def test_write_and_read_round_trip(self, db):
        from ai_mailbox.db.queries import get_user_profile_metadata, update_user_profile_metadata
        data = {"team": "product", "department": "engineering", "bio": "MCP developer"}
        update_user_profile_metadata(db, "keith", data)
        meta = get_user_profile_metadata(db, "keith")
        assert meta == data

    def test_overwrites_previous(self, db):
        from ai_mailbox.db.queries import get_user_profile_metadata, update_user_profile_metadata
        update_user_profile_metadata(db, "keith", {"team": "old"})
        update_user_profile_metadata(db, "keith", {"team": "new"})
        meta = get_user_profile_metadata(db, "keith")
        assert meta["team"] == "new"

    def test_stores_list_fields(self, db):
        from ai_mailbox.db.queries import get_user_profile_metadata, update_user_profile_metadata
        data = {
            "expertise_tags": ["python", "mcp", "fastapi"],
            "projects": ["ai-mailbox", "steertrue"],
            "jira_tickets": ["BTSD-100", "BTSD-200"],
            "observed_topics": ["oauth", "websockets"],
        }
        update_user_profile_metadata(db, "keith", data)
        meta = get_user_profile_metadata(db, "keith")
        assert set(meta["expertise_tags"]) == {"python", "mcp", "fastapi"}
        assert "ai-mailbox" in meta["projects"]


# ---------------------------------------------------------------------------
# Tool layer
# ---------------------------------------------------------------------------

class TestUpdateProfileTool:
    """mailbox_update_profile tool."""

    def test_basic_update(self, db):
        from ai_mailbox.tools.update_profile import tool_update_profile
        result = tool_update_profile(db, user_id="keith", metadata={"team": "eng"})
        assert result["user_id"] == "keith"
        assert result["profile_metadata"]["team"] == "eng"

    def test_merge_mode_unions_lists(self, db):
        from ai_mailbox.tools.update_profile import tool_update_profile
        tool_update_profile(db, user_id="keith", metadata={"expertise_tags": ["python"]})
        result = tool_update_profile(db, user_id="keith", metadata={"expertise_tags": ["mcp"]})
        tags = result["profile_metadata"]["expertise_tags"]
        assert "python" in tags
        assert "mcp" in tags

    def test_merge_mode_replaces_strings(self, db):
        from ai_mailbox.tools.update_profile import tool_update_profile
        tool_update_profile(db, user_id="keith", metadata={"team": "old"})
        result = tool_update_profile(db, user_id="keith", metadata={"team": "new"})
        assert result["profile_metadata"]["team"] == "new"

    def test_replace_mode_overwrites(self, db):
        from ai_mailbox.tools.update_profile import tool_update_profile
        tool_update_profile(db, user_id="keith", metadata={"team": "eng", "bio": "dev"})
        result = tool_update_profile(db, user_id="keith", metadata={"team": "product"}, merge=False)
        assert result["profile_metadata"] == {"team": "product"}
        assert "bio" not in result["profile_metadata"]

    def test_rejects_unknown_keys(self, db):
        from ai_mailbox.tools.update_profile import tool_update_profile
        result = tool_update_profile(db, user_id="keith", metadata={"hacker_field": "bad"})
        assert "error" in result
        assert result["error"]["code"] == "INVALID_PARAMETER"

    def test_rejects_non_list_expertise_tags(self, db):
        from ai_mailbox.tools.update_profile import tool_update_profile
        result = tool_update_profile(db, user_id="keith", metadata={"expertise_tags": "not a list"})
        assert "error" in result
        assert result["error"]["code"] == "INVALID_PARAMETER"

    def test_rejects_non_string_items_in_list(self, db):
        from ai_mailbox.tools.update_profile import tool_update_profile
        result = tool_update_profile(db, user_id="keith", metadata={"expertise_tags": [1, 2, 3]})
        assert "error" in result

    def test_rejects_too_many_expertise_tags(self, db):
        from ai_mailbox.tools.update_profile import tool_update_profile
        tags = [f"tag-{i}" for i in range(MAX_EXPERTISE_TAGS + 1)]
        result = tool_update_profile(db, user_id="keith", metadata={"expertise_tags": tags})
        assert "error" in result

    def test_rejects_oversized_metadata(self, db):
        from ai_mailbox.tools.update_profile import tool_update_profile
        huge = {"bio": "x" * MAX_PROFILE_METADATA_SIZE}
        result = tool_update_profile(db, user_id="keith", metadata=huge)
        assert "error" in result
        assert result["error"]["code"] == "PROFILE_TOO_LARGE"

    def test_empty_metadata_is_valid(self, db):
        from ai_mailbox.tools.update_profile import tool_update_profile
        result = tool_update_profile(db, user_id="keith", metadata={})
        assert "error" not in result

    def test_system_user_denied(self, db):
        from ai_mailbox.tools.update_profile import tool_update_profile
        result = tool_update_profile(db, user_id="system", metadata={"team": "eng"})
        assert "error" in result
        assert result["error"]["code"] == "SYSTEM_USER_DENIED"

    def test_merge_deduplicates_list_items(self, db):
        from ai_mailbox.tools.update_profile import tool_update_profile
        tool_update_profile(db, user_id="keith", metadata={"expertise_tags": ["python", "mcp"]})
        result = tool_update_profile(db, user_id="keith", metadata={"expertise_tags": ["python", "fastapi"]})
        tags = result["profile_metadata"]["expertise_tags"]
        assert tags.count("python") == 1
        assert "fastapi" in tags
        assert "mcp" in tags
