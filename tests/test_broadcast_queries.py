"""Broadcast queue query functions -- create, get, claim, release, gates, matching."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from ai_mailbox.config import BROADCAST_COOLDOWN_HOURS, BROADCAST_DEFAULT_EXPIRY_HOURS


class TestCreateBroadcastRequest:

    def test_creates_with_defaults(self, db):
        from ai_mailbox.db.queries import create_broadcast_request
        result = create_broadcast_request(
            db, from_user="keith", question="Help with workato?",
            source_context="Recipe failing", tags=["workato", "integrations"],
        )
        assert "id" in result
        assert result["status"] == "open"
        assert result["from_user"] == "keith"
        assert result["question"] == "Help with workato?"
        assert result["expires_at"] is not None

    def test_stores_tags_as_json(self, db):
        from ai_mailbox.db.queries import create_broadcast_request, get_broadcast_request
        result = create_broadcast_request(
            db, from_user="keith", question="q",
            tags=["hr", "benefits"],
        )
        br = get_broadcast_request(db, result["id"])
        tags = json.loads(br["tags"])
        assert tags == ["hr", "benefits"]

    def test_empty_tags_allowed(self, db):
        from ai_mailbox.db.queries import create_broadcast_request
        result = create_broadcast_request(
            db, from_user="keith", question="General question",
            tags=[],
        )
        assert result["status"] == "open"

    def test_custom_project(self, db):
        from ai_mailbox.db.queries import create_broadcast_request, get_broadcast_request
        result = create_broadcast_request(
            db, from_user="keith", question="q",
            tags=["test"], project="ai-mailbox",
        )
        br = get_broadcast_request(db, result["id"])
        assert br["project"] == "ai-mailbox"


class TestGetBroadcastRequest:

    def test_returns_none_for_missing(self, db):
        from ai_mailbox.db.queries import get_broadcast_request
        assert get_broadcast_request(db, "nonexistent") is None

    def test_returns_full_record(self, db):
        from ai_mailbox.db.queries import create_broadcast_request, get_broadcast_request
        created = create_broadcast_request(
            db, from_user="keith", question="test?",
            source_context="ctx", tags=["t1"],
        )
        br = get_broadcast_request(db, created["id"])
        assert br["question"] == "test?"
        assert br["source_context"] == "ctx"


class TestGetOpenBroadcastsForUser:
    """Match broadcasts against user's full profile."""

    def test_matches_expertise_tags(self, db):
        from ai_mailbox.db.queries import (
            create_broadcast_request, get_open_broadcasts_for_user,
            update_user_profile_metadata,
        )
        update_user_profile_metadata(db, "amy", {"expertise_tags": ["hr", "onboarding"]})
        create_broadcast_request(db, from_user="keith", question="HR help?", tags=["hr"])
        results = get_open_broadcasts_for_user(db, "amy")
        assert len(results) == 1
        assert results[0]["match_score"] >= 1

    def test_matches_observed_topics(self, db):
        from ai_mailbox.db.queries import (
            create_broadcast_request, get_open_broadcasts_for_user,
            update_user_profile_metadata,
        )
        update_user_profile_metadata(db, "amy", {"observed_topics": ["workato"]})
        create_broadcast_request(db, from_user="keith", question="Workato help?", tags=["workato"])
        results = get_open_broadcasts_for_user(db, "amy")
        assert len(results) == 1

    def test_matches_projects(self, db):
        from ai_mailbox.db.queries import (
            create_broadcast_request, get_open_broadcasts_for_user,
            update_user_profile_metadata,
        )
        update_user_profile_metadata(db, "amy", {"projects": ["pricing-model"]})
        create_broadcast_request(db, from_user="keith", question="Pricing?", tags=["pricing-model"])
        results = get_open_broadcasts_for_user(db, "amy")
        assert len(results) == 1

    def test_expertise_scores_higher_than_observed(self, db):
        from ai_mailbox.db.queries import (
            create_broadcast_request, get_open_broadcasts_for_user,
            update_user_profile_metadata,
        )
        update_user_profile_metadata(db, "keith", {"expertise_tags": ["compliance"]})
        update_user_profile_metadata(db, "amy", {"observed_topics": ["compliance"]})
        create_broadcast_request(db, from_user="system", question="Compliance?", tags=["compliance"])
        # Both should match but keith scores higher (expertise=2 vs observed=1)
        results_keith = get_open_broadcasts_for_user(db, "keith")
        results_amy = get_open_broadcasts_for_user(db, "amy")
        assert results_keith[0]["match_score"] > results_amy[0]["match_score"]

    def test_excludes_own_requests(self, db):
        from ai_mailbox.db.queries import (
            create_broadcast_request, get_open_broadcasts_for_user,
            update_user_profile_metadata,
        )
        update_user_profile_metadata(db, "keith", {"expertise_tags": ["python"]})
        create_broadcast_request(db, from_user="keith", question="Python help?", tags=["python"])
        results = get_open_broadcasts_for_user(db, "keith")
        assert len(results) == 0

    def test_excludes_cooldown(self, db):
        from ai_mailbox.db.queries import (
            create_broadcast_request, get_open_broadcasts_for_user,
            update_user_profile_metadata, claim_broadcast, decline_gate1,
        )
        update_user_profile_metadata(db, "amy", {"expertise_tags": ["hr"]})
        br = create_broadcast_request(db, from_user="keith", question="HR?", tags=["hr"])
        claim_broadcast(db, br["id"], "amy")
        decline_gate1(db, br["id"], "amy")
        # Amy should not see it during cooldown
        results = get_open_broadcasts_for_user(db, "amy")
        assert len(results) == 0

    def test_no_match_returns_empty(self, db):
        from ai_mailbox.db.queries import (
            create_broadcast_request, get_open_broadcasts_for_user,
            update_user_profile_metadata,
        )
        update_user_profile_metadata(db, "amy", {"expertise_tags": ["finance"]})
        create_broadcast_request(db, from_user="keith", question="Python?", tags=["python"])
        results = get_open_broadcasts_for_user(db, "amy")
        assert len(results) == 0


class TestClaimBroadcast:

    def test_creates_claim(self, db):
        from ai_mailbox.db.queries import create_broadcast_request, claim_broadcast
        br = create_broadcast_request(db, from_user="keith", question="Help?", tags=["hr"])
        claim = claim_broadcast(db, br["id"], "amy")
        assert claim["status"] == "claimed"
        assert claim["claimant_id"] == "amy"

    def test_sets_broadcast_status_claimed(self, db):
        from ai_mailbox.db.queries import (
            create_broadcast_request, claim_broadcast, get_broadcast_request,
        )
        br = create_broadcast_request(db, from_user="keith", question="Help?", tags=["hr"])
        claim_broadcast(db, br["id"], "amy")
        updated = get_broadcast_request(db, br["id"])
        assert updated["status"] == "claimed"

    def test_cannot_double_claim(self, db):
        from ai_mailbox.db.queries import create_broadcast_request, claim_broadcast
        br = create_broadcast_request(db, from_user="keith", question="Help?", tags=["hr"])
        claim_broadcast(db, br["id"], "amy")
        result = claim_broadcast(db, br["id"], "amy")
        assert "error" in result


class TestGate1:

    def test_approve_sets_drafting(self, db):
        from ai_mailbox.db.queries import (
            create_broadcast_request, claim_broadcast, approve_gate1,
        )
        br = create_broadcast_request(db, from_user="keith", question="Help?", tags=["hr"])
        claim_broadcast(db, br["id"], "amy")
        result = approve_gate1(db, br["id"], "amy")
        assert result["status"] == "drafting"

    def test_decline_releases_to_pool(self, db):
        from ai_mailbox.db.queries import (
            create_broadcast_request, claim_broadcast, decline_gate1,
            get_broadcast_request,
        )
        br = create_broadcast_request(db, from_user="keith", question="Help?", tags=["hr"])
        claim_broadcast(db, br["id"], "amy")
        decline_gate1(db, br["id"], "amy")
        updated = get_broadcast_request(db, br["id"])
        assert updated["status"] == "open"

    def test_decline_sets_cooldown(self, db):
        from ai_mailbox.db.queries import (
            create_broadcast_request, claim_broadcast, decline_gate1,
        )
        br = create_broadcast_request(db, from_user="keith", question="Help?", tags=["hr"])
        claim_broadcast(db, br["id"], "amy")
        result = decline_gate1(db, br["id"], "amy")
        assert result["cooldown_until"] is not None


class TestGate2:

    def _setup_drafting(self, db):
        from ai_mailbox.db.queries import (
            create_broadcast_request, claim_broadcast, approve_gate1, submit_draft,
        )
        br = create_broadcast_request(db, from_user="keith", question="Help?", tags=["hr"])
        claim_broadcast(db, br["id"], "amy")
        approve_gate1(db, br["id"], "amy")
        submit_draft(db, br["id"], "amy", "The answer is 42.")
        return br

    def test_submit_draft_sets_pending_review(self, db):
        from ai_mailbox.db.queries import (
            create_broadcast_request, claim_broadcast, approve_gate1, submit_draft,
        )
        br = create_broadcast_request(db, from_user="keith", question="Help?", tags=["hr"])
        claim_broadcast(db, br["id"], "amy")
        approve_gate1(db, br["id"], "amy")
        result = submit_draft(db, br["id"], "amy", "Draft answer here.")
        assert result["status"] == "pending_review"

    def test_approve_gate2_fulfills(self, db):
        from ai_mailbox.db.queries import approve_gate2, get_broadcast_request
        br = self._setup_drafting(db)
        result = approve_gate2(db, br["id"], "amy")
        assert result["status"] == "fulfilled"
        updated = get_broadcast_request(db, br["id"])
        assert updated["status"] == "fulfilled"

    def test_reject_gate2_allows_redraft(self, db):
        from ai_mailbox.db.queries import reject_gate2
        br = self._setup_drafting(db)
        result = reject_gate2(db, br["id"], "amy")
        assert result["status"] == "rejected"


class TestGetMyBroadcasts:

    def test_returns_own_broadcasts(self, db):
        from ai_mailbox.db.queries import create_broadcast_request, get_my_broadcasts
        create_broadcast_request(db, from_user="keith", question="Q1", tags=["t1"])
        create_broadcast_request(db, from_user="keith", question="Q2", tags=["t2"])
        results = get_my_broadcasts(db, "keith")
        assert len(results) == 2

    def test_excludes_others(self, db):
        from ai_mailbox.db.queries import create_broadcast_request, get_my_broadcasts
        create_broadcast_request(db, from_user="keith", question="Q1", tags=["t1"])
        create_broadcast_request(db, from_user="amy", question="Q2", tags=["t2"])
        results = get_my_broadcasts(db, "keith")
        assert len(results) == 1

    def test_filter_by_status(self, db):
        from ai_mailbox.db.queries import create_broadcast_request, get_my_broadcasts
        create_broadcast_request(db, from_user="keith", question="Q1", tags=["t1"])
        results = get_my_broadcasts(db, "keith", status="fulfilled")
        assert len(results) == 0


class TestGetMyClaims:

    def test_returns_own_claims(self, db):
        from ai_mailbox.db.queries import (
            create_broadcast_request, claim_broadcast, get_my_claims,
        )
        br = create_broadcast_request(db, from_user="keith", question="Help?", tags=["hr"])
        claim_broadcast(db, br["id"], "amy")
        results = get_my_claims(db, "amy")
        assert len(results) == 1
        assert results[0]["question"] == "Help?"

    def test_excludes_others_claims(self, db):
        from ai_mailbox.db.queries import (
            create_broadcast_request, claim_broadcast, get_my_claims,
        )
        br = create_broadcast_request(db, from_user="keith", question="Help?", tags=["hr"])
        claim_broadcast(db, br["id"], "amy")
        results = get_my_claims(db, "keith")
        assert len(results) == 0
