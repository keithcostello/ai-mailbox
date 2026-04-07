"""find_experts: directory lookup for AI-to-AI routing by expertise tags."""

from __future__ import annotations

import pytest

from ai_mailbox.config import MAX_FIND_EXPERTS_TAGS


# ---------------------------------------------------------------------------
# Query layer
# ---------------------------------------------------------------------------

class TestFindExpertsByTagsQuery:
    """find_experts_by_tags returns ranked matches."""

    def test_single_tag_match(self, db):
        from ai_mailbox.db.queries import find_experts_by_tags, update_user_profile_metadata
        update_user_profile_metadata(db, "amy", {"expertise_tags": ["hr", "onboarding"]})
        results = find_experts_by_tags(db, ["hr"])
        assert len(results) == 1
        assert results[0]["user_id"] == "amy"
        assert results[0]["match_score"] == 1

    def test_multi_tag_ranking(self, db, bob):
        from ai_mailbox.db.queries import find_experts_by_tags, update_user_profile_metadata
        update_user_profile_metadata(db, "amy", {"expertise_tags": ["hr", "onboarding", "benefits"]})
        update_user_profile_metadata(db, bob, {"expertise_tags": ["hr"]})
        results = find_experts_by_tags(db, ["hr", "onboarding"])
        assert len(results) == 2
        assert results[0]["user_id"] == "amy"  # 2 matches
        assert results[0]["match_score"] == 2
        assert results[1]["user_id"] == bob  # 1 match
        assert results[1]["match_score"] == 1

    def test_no_matches(self, db):
        from ai_mailbox.db.queries import find_experts_by_tags, update_user_profile_metadata
        update_user_profile_metadata(db, "amy", {"expertise_tags": ["finance"]})
        results = find_experts_by_tags(db, ["quantum_physics"])
        assert results == []

    def test_excludes_caller(self, db):
        from ai_mailbox.db.queries import find_experts_by_tags, update_user_profile_metadata
        update_user_profile_metadata(db, "keith", {"expertise_tags": ["python"]})
        update_user_profile_metadata(db, "amy", {"expertise_tags": ["python"]})
        results = find_experts_by_tags(db, ["python"], exclude_user="keith")
        assert len(results) == 1
        assert results[0]["user_id"] == "amy"

    def test_respects_limit(self, db, bob):
        from ai_mailbox.db.queries import find_experts_by_tags, update_user_profile_metadata
        update_user_profile_metadata(db, "keith", {"expertise_tags": ["python"]})
        update_user_profile_metadata(db, "amy", {"expertise_tags": ["python"]})
        update_user_profile_metadata(db, bob, {"expertise_tags": ["python"]})
        results = find_experts_by_tags(db, ["python"], limit=2)
        assert len(results) == 2

    def test_empty_profile_ignored(self, db):
        from ai_mailbox.db.queries import find_experts_by_tags
        # keith and amy have default empty profiles
        results = find_experts_by_tags(db, ["python"])
        assert results == []

    def test_excludes_system_user(self, db):
        from ai_mailbox.db.queries import find_experts_by_tags, update_user_profile_metadata
        update_user_profile_metadata(db, "system", {"expertise_tags": ["everything"]})
        results = find_experts_by_tags(db, ["everything"])
        assert all(r["user_id"] != "system" for r in results)

    def test_returns_bio_and_display_name(self, db):
        from ai_mailbox.db.queries import find_experts_by_tags, update_user_profile_metadata
        update_user_profile_metadata(db, "amy", {
            "expertise_tags": ["hr"],
            "bio": "HR specialist",
        })
        results = find_experts_by_tags(db, ["hr"])
        assert results[0]["display_name"] == "Amy"
        assert results[0]["bio"] == "HR specialist"

    def test_matched_tags_in_result(self, db):
        from ai_mailbox.db.queries import find_experts_by_tags, update_user_profile_metadata
        update_user_profile_metadata(db, "amy", {"expertise_tags": ["hr", "onboarding", "payroll"]})
        results = find_experts_by_tags(db, ["hr", "payroll", "taxes"])
        assert set(results[0]["matched_tags"]) == {"hr", "payroll"}

    def test_case_sensitive(self, db):
        from ai_mailbox.db.queries import find_experts_by_tags, update_user_profile_metadata
        update_user_profile_metadata(db, "amy", {"expertise_tags": ["Python"]})
        results = find_experts_by_tags(db, ["python"])
        # Tags are case-sensitive by default
        assert results == []


# ---------------------------------------------------------------------------
# Tool layer
# ---------------------------------------------------------------------------

class TestFindExpertsTool:
    """mailbox_find_experts tool."""

    def test_basic_search(self, db):
        from ai_mailbox.db.queries import update_user_profile_metadata
        from ai_mailbox.tools.find_experts import tool_find_experts
        update_user_profile_metadata(db, "amy", {"expertise_tags": ["hr"], "bio": "HR lead"})
        result = tool_find_experts(db, user_id="keith", tags=["hr"])
        assert result["result_count"] == 1
        assert result["experts"][0]["user_id"] == "amy"
        assert result["query_tags"] == ["hr"]

    def test_excludes_self(self, db):
        from ai_mailbox.db.queries import update_user_profile_metadata
        from ai_mailbox.tools.find_experts import tool_find_experts
        update_user_profile_metadata(db, "keith", {"expertise_tags": ["python"]})
        update_user_profile_metadata(db, "amy", {"expertise_tags": ["python"]})
        result = tool_find_experts(db, user_id="keith", tags=["python"])
        ids = [e["user_id"] for e in result["experts"]]
        assert "keith" not in ids

    def test_rejects_empty_tags(self, db):
        from ai_mailbox.tools.find_experts import tool_find_experts
        result = tool_find_experts(db, user_id="keith", tags=[])
        assert "error" in result

    def test_rejects_too_many_tags(self, db):
        from ai_mailbox.tools.find_experts import tool_find_experts
        tags = [f"tag-{i}" for i in range(MAX_FIND_EXPERTS_TAGS + 1)]
        result = tool_find_experts(db, user_id="keith", tags=tags)
        assert "error" in result

    def test_rejects_invalid_limit(self, db):
        from ai_mailbox.tools.find_experts import tool_find_experts
        result = tool_find_experts(db, user_id="keith", tags=["hr"], limit=0)
        assert "error" in result
        result2 = tool_find_experts(db, user_id="keith", tags=["hr"], limit=100)
        assert "error" in result2

    def test_includes_instruction(self, db):
        from ai_mailbox.tools.find_experts import tool_find_experts
        result = tool_find_experts(db, user_id="keith", tags=["hr"])
        assert "instruction" in result

    def test_no_results_returns_empty(self, db):
        from ai_mailbox.tools.find_experts import tool_find_experts
        result = tool_find_experts(db, user_id="keith", tags=["quantum"])
        assert result["result_count"] == 0
        assert result["experts"] == []
