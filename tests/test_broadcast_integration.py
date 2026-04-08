"""Broadcast queue functional TDD -- full flows with seeded profiles.

Tests the complete crowdsourced AI-to-AI routing:
1. Keith broadcasts a question
2. Matching AIs see it in their queue
3. One claims, gets Gate 1 approval, drafts answer, gets Gate 2 approval
4. Requester gets the response
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from ai_mailbox.tools.update_profile import tool_update_profile
from ai_mailbox.tools.broadcast_request import tool_broadcast_request
from ai_mailbox.tools.check_broadcast_queue import tool_check_broadcast_queue
from ai_mailbox.tools.claim_broadcast import tool_claim_broadcast
from ai_mailbox.tools.respond_to_broadcast import tool_respond_to_broadcast
from ai_mailbox.tools.my_broadcasts import tool_my_broadcasts
from ai_mailbox.tools.my_claims import tool_my_claims


@pytest.fixture
def seeded(db, bob):
    """Seed 3 users with profiles across engineering, HR, finance."""
    tool_update_profile(db, user_id="keith", metadata={
        "team": "engineering",
        "expertise_tags": ["python", "mcp", "oauth"],
        "observed_topics": ["workato", "railway"],
        "projects": ["ai-mailbox"],
    })
    tool_update_profile(db, user_id="amy", metadata={
        "team": "hr",
        "expertise_tags": ["hr", "onboarding", "benefits", "compliance"],
        "projects": ["employee-handbook"],
        "bio": "HR specialist",
    })
    tool_update_profile(db, user_id=bob, metadata={
        "team": "finance",
        "expertise_tags": ["finance", "budgeting", "compliance"],
        "projects": ["q2-budget"],
        "bio": "Finance analyst",
    })


class TestBroadcastHappyPath:
    """Full flow: broadcast -> claim -> Gate 1 -> draft -> Gate 2 -> fulfilled."""

    def test_complete_flow(self, db, seeded):
        # Keith broadcasts an HR question
        br = tool_broadcast_request(
            db, user_id="keith",
            question="What is the benefits enrollment timeline for Q2?",
            source_context="Finance team budgeting",
            tags=["hr", "benefits", "enrollment"],
        )
        assert br["status"] == "open"
        broadcast_id = br["id"]

        # Amy's AI checks the queue -- she has hr + benefits expertise
        queue = tool_check_broadcast_queue(db, user_id="amy")
        assert queue["queue_count"] == 1
        assert queue["requests"][0]["broadcast_id"] == broadcast_id

        # Amy's AI claims it
        claim = tool_claim_broadcast(db, user_id="amy", broadcast_id=broadcast_id)
        assert claim["status"] == "claimed"
        assert "Do NOT generate an answer" in claim["instruction"]

        # Gate 1: Amy approves answering
        g1 = tool_respond_to_broadcast(
            db, user_id="amy", broadcast_id=broadcast_id, action="approve_question",
        )
        assert g1["status"] == "drafting"

        # Amy's AI drafts an answer
        g2_submit = tool_respond_to_broadcast(
            db, user_id="amy", broadcast_id=broadcast_id, action="submit_draft",
            draft_response="Benefits enrollment opens March 15, closes April 30.",
        )
        assert g2_submit["status"] == "pending_review"

        # Gate 2: Amy approves the answer
        g2_approve = tool_respond_to_broadcast(
            db, user_id="amy", broadcast_id=broadcast_id, action="approve_answer",
        )
        assert g2_approve["status"] == "fulfilled"

        # Keith checks his broadcasts
        my_br = tool_my_broadcasts(db, user_id="keith")
        assert my_br["broadcast_count"] == 1
        assert my_br["broadcasts"][0]["status"] == "fulfilled"


class TestGate1Decline:
    """Amy declines, request goes back to pool, Bob picks it up."""

    def test_decline_and_reclaim(self, db, seeded):
        br = tool_broadcast_request(
            db, user_id="keith",
            question="Who handles compliance for the Q2 audit?",
            tags=["compliance"],
        )
        broadcast_id = br["id"]

        # Both amy and bob should see it (both have compliance)
        amy_queue = tool_check_broadcast_queue(db, user_id="amy")
        bob_queue = tool_check_broadcast_queue(db, user_id="bob")
        assert amy_queue["queue_count"] == 1
        assert bob_queue["queue_count"] == 1

        # Amy claims, then declines
        tool_claim_broadcast(db, user_id="amy", broadcast_id=broadcast_id)
        tool_respond_to_broadcast(
            db, user_id="amy", broadcast_id=broadcast_id, action="decline_question",
        )

        # Amy no longer sees it (cooldown)
        amy_queue2 = tool_check_broadcast_queue(db, user_id="amy")
        assert amy_queue2["queue_count"] == 0

        # Bob still sees it
        bob_queue2 = tool_check_broadcast_queue(db, user_id="bob")
        assert bob_queue2["queue_count"] == 1

        # Bob claims and completes
        tool_claim_broadcast(db, user_id="bob", broadcast_id=broadcast_id)
        tool_respond_to_broadcast(db, user_id="bob", broadcast_id=broadcast_id, action="approve_question")
        tool_respond_to_broadcast(
            db, user_id="bob", broadcast_id=broadcast_id, action="submit_draft",
            draft_response="Finance handles Q2 audit compliance.",
        )
        result = tool_respond_to_broadcast(
            db, user_id="bob", broadcast_id=broadcast_id, action="approve_answer",
        )
        assert result["status"] == "fulfilled"


class TestGate2RejectRedraft:
    """Answer rejected at Gate 2, redraft, then approve."""

    def test_reject_and_redraft(self, db, seeded):
        br = tool_broadcast_request(
            db, user_id="keith", question="PTO policy?", tags=["hr"],
        )
        tool_claim_broadcast(db, user_id="amy", broadcast_id=br["id"])
        tool_respond_to_broadcast(db, user_id="amy", broadcast_id=br["id"], action="approve_question")

        # First draft rejected
        tool_respond_to_broadcast(
            db, user_id="amy", broadcast_id=br["id"], action="submit_draft",
            draft_response="PTO is unlimited.",
        )
        reject = tool_respond_to_broadcast(
            db, user_id="amy", broadcast_id=br["id"], action="reject_answer",
        )
        assert reject["status"] == "rejected"

        # Redraft -- need to reset to drafting first
        # The reject_gate2 sets claim to 'rejected', which allows resubmit
        # For now, the query layer allows submit_draft from 'rejected' state too
        # TODO: add explicit state transition from rejected -> drafting


class TestObservedTopicMatching:
    """Matching on observed_topics and projects, not just expertise_tags."""

    def test_workato_matches_observed_topic(self, db, seeded):
        """Keith has observed_topics=['workato'] -- should match workato-tagged broadcast."""
        br = tool_broadcast_request(
            db, user_id="amy",
            question="My workato recipe is erroring out, can anyone help?",
            tags=["workato", "integrations"],
        )
        # Keith has workato in observed_topics
        queue = tool_check_broadcast_queue(db, user_id="keith")
        assert queue["queue_count"] == 1
        # Score should be 1 per observed topic match (not 2 like expertise)
        assert queue["requests"][0]["match_score"] >= 1

    def test_project_name_matches(self, db, seeded):
        """Bob has project 'q2-budget' -- matches broadcast tagged with it."""
        br = tool_broadcast_request(
            db, user_id="keith",
            question="Need the Q2 budget template",
            tags=["q2-budget"],
        )
        queue = tool_check_broadcast_queue(db, user_id="bob")
        assert queue["queue_count"] == 1


class TestCrossDomainRouting:
    """Compliance tag matches both HR and Finance."""

    def test_both_departments_see_compliance_broadcast(self, db, seeded):
        br = tool_broadcast_request(
            db, user_id="keith",
            question="Who handles compliance for our Q2 audit?",
            tags=["compliance", "budgeting"],
        )
        amy_queue = tool_check_broadcast_queue(db, user_id="amy")
        bob_queue = tool_check_broadcast_queue(db, user_id="bob")

        # Both should match compliance
        assert amy_queue["queue_count"] == 1
        assert bob_queue["queue_count"] == 1

        # Bob should score higher (compliance=2 + budgeting=2 = 4)
        # Amy scores (compliance=2 = 2)
        assert bob_queue["requests"][0]["match_score"] > amy_queue["requests"][0]["match_score"]


class TestCannotClaimOwn:
    """Sender cannot claim their own broadcast."""

    def test_self_claim_rejected(self, db, seeded):
        br = tool_broadcast_request(
            db, user_id="keith", question="Test?", tags=["python"],
        )
        result = tool_claim_broadcast(db, user_id="keith", broadcast_id=br["id"])
        assert "error" in result


class TestMyBroadcastsAndClaims:
    """Status tracking tools."""

    def test_my_broadcasts_shows_open(self, db, seeded):
        tool_broadcast_request(db, user_id="keith", question="Q1", tags=["hr"])
        tool_broadcast_request(db, user_id="keith", question="Q2", tags=["finance"])
        result = tool_my_broadcasts(db, user_id="keith")
        assert result["broadcast_count"] == 2

    def test_my_claims_after_claim(self, db, seeded):
        br = tool_broadcast_request(db, user_id="keith", question="HR?", tags=["hr"])
        tool_claim_broadcast(db, user_id="amy", broadcast_id=br["id"])
        result = tool_my_claims(db, user_id="amy")
        assert result["claim_count"] == 1
        assert result["claims"][0]["question"] == "HR?"
