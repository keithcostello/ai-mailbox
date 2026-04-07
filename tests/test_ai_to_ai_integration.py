"""AI-to-AI integration test -- full flow with seeded profiles.

This test simulates the real-world ai-to-ai scenario:
1. Three users with different expertise profiles
2. User A searches for an expert
3. User A sends an ai-to-ai request
4. User B's AI drafts a response (pending approval)
5. User B approves the response
6. The full conversation is visible to both parties

Run with: py -m pytest tests/test_ai_to_ai_integration.py -v
"""

from __future__ import annotations

import json

import pytest

from ai_mailbox.db import queries
from ai_mailbox.tools.update_profile import tool_update_profile
from ai_mailbox.tools.find_experts import tool_find_experts
from ai_mailbox.tools.send import tool_send_message
from ai_mailbox.tools.approve_ai_response import tool_approve_ai_response
from ai_mailbox.tools.list_messages import tool_list_messages
from ai_mailbox.tools.identity import tool_whoami


@pytest.fixture
def seeded_profiles(db, bob):
    """Seed three users with distinct expertise profiles."""
    tool_update_profile(db, user_id="keith", metadata={
        "team": "engineering",
        "department": "platform",
        "expertise_tags": ["python", "mcp", "oauth", "fastapi", "railway"],
        "projects": ["ai-mailbox", "steertrue"],
        "bio": "Platform engineer building AI infrastructure",
    })
    tool_update_profile(db, user_id="amy", metadata={
        "team": "hr",
        "department": "people-ops",
        "expertise_tags": ["hr", "onboarding", "benefits", "compliance", "payroll"],
        "projects": ["employee-handbook", "benefits-portal"],
        "bio": "HR specialist handling onboarding and benefits",
    })
    tool_update_profile(db, user_id=bob, metadata={
        "team": "finance",
        "department": "accounting",
        "expertise_tags": ["finance", "budgeting", "forecasting", "compliance"],
        "projects": ["q2-budget", "expense-automation"],
        "bio": "Finance analyst focused on budgeting and compliance",
    })
    return {"keith": "keith", "amy": "amy", "bob": bob}


class TestAiToAiIntegrationFlow:
    """Full ai-to-ai scenario with seeded profiles."""

    def test_profiles_visible_in_whoami(self, db, seeded_profiles):
        """whoami shows profile_metadata."""
        result = tool_whoami(db, user_id="keith")
        assert result["profile_metadata"]["team"] == "engineering"
        assert "python" in result["profile_metadata"]["expertise_tags"]

    def test_find_hr_expert(self, db, seeded_profiles):
        """Keith searches for HR expertise, finds Amy."""
        result = tool_find_experts(db, user_id="keith", tags=["hr", "onboarding"])
        assert result["result_count"] == 1
        assert result["experts"][0]["user_id"] == "amy"
        assert result["experts"][0]["match_score"] == 2

    def test_find_compliance_expert_returns_multiple(self, db, seeded_profiles):
        """Compliance tag matches both Amy (HR compliance) and Bob (finance compliance)."""
        result = tool_find_experts(db, user_id="keith", tags=["compliance"])
        assert result["result_count"] == 2
        ids = [e["user_id"] for e in result["experts"]]
        assert "amy" in ids
        assert "bob" in ids

    def test_find_python_expert_excludes_self(self, db, seeded_profiles):
        """Keith has python tag but is excluded from his own search."""
        result = tool_find_experts(db, user_id="keith", tags=["python"])
        ids = [e["user_id"] for e in result["experts"]]
        assert "keith" not in ids

    def test_full_ai_to_ai_flow(self, db, seeded_profiles):
        """Complete flow: find -> request -> draft response -> approve -> verify."""
        # Step 1: Keith's AI finds an HR expert
        experts = tool_find_experts(db, user_id="keith", tags=["hr", "benefits"])
        assert experts["experts"][0]["user_id"] == "amy"

        # Step 2: Keith's AI sends an ai-to-ai request to Amy
        request_body = json.dumps({
            "question": "What is the benefits enrollment timeline for Q2?",
            "source_context": "Finance team needs to budget for benefits costs in Q2 planning",
            "tags": ["hr", "benefits", "enrollment", "q2"],
        })
        req = tool_send_message(
            db, user_id="keith", to="amy", body=request_body,
            content_type="ai-to-ai/request",
        )
        assert "message_id" in req
        assert "conversation_id" in req

        # Step 3: Amy's AI sees the request in her inbox
        amy_msgs = tool_list_messages(db, user_id="amy", unread_only=True)
        ai_requests = [
            m for m in amy_msgs["messages"]
            if m.get("content_type") == "ai-to-ai/request"
        ]
        assert len(ai_requests) >= 1

        # Step 4: Amy's AI drafts a response (requires human approval)
        response_body = json.dumps({
            "draft_response": (
                "Benefits enrollment for Q2 opens March 15 and closes April 30. "
                "New hires have a 30-day enrollment window from start date. "
                "Contact HR portal for plan options and rates."
            ),
            "requires_human_approval": True,
        })
        resp = tool_send_message(
            db, user_id="amy", to="keith", body=response_body,
            content_type="ai-to-ai/response",
        )
        assert "message_id" in resp

        # Step 5: Verify the response is pending approval
        msg = queries.get_message(db, resp["message_id"])
        assert msg["approval_status"] == "pending_human_approval"

        # Step 6: Amy (human) approves the response
        approval = tool_approve_ai_response(
            db, user_id="amy", message_id=resp["message_id"], action="approve",
        )
        assert approval["approval_status"] == "approved"

        # Step 7: Keith sees the approved response
        keith_msgs = tool_list_messages(db, user_id="keith", unread_only=True)
        ai_responses = [
            m for m in keith_msgs["messages"]
            if m.get("content_type") == "ai-to-ai/response"
        ]
        assert len(ai_responses) >= 1

        # Step 8: Thread has the full conversation
        thread = queries.get_conversation_messages(db, req["conversation_id"])
        msgs, _ = thread
        content_types = [m.get("content_type") for m in msgs]
        assert "ai-to-ai/request" in content_types
        assert "ai-to-ai/response" in content_types
        # System message for the request
        system_msgs = [m for m in msgs if m["from_user"] == "system"]
        assert len(system_msgs) >= 1

    def test_rejection_flow(self, db, seeded_profiles):
        """Amy's AI drafts a response but Amy rejects it."""
        # Send request
        request_body = json.dumps({
            "question": "What's the PTO policy?",
            "source_context": "New hire asking about time off",
            "tags": ["hr", "pto"],
        })
        req = tool_send_message(
            db, user_id="keith", to="amy", body=request_body,
            content_type="ai-to-ai/request",
        )

        # Amy's AI drafts response
        response_body = json.dumps({
            "draft_response": "PTO is unlimited but this might be wrong.",
            "requires_human_approval": True,
        })
        resp = tool_send_message(
            db, user_id="amy", to="keith", body=response_body,
            content_type="ai-to-ai/response",
        )

        # Amy rejects
        rejection = tool_approve_ai_response(
            db, user_id="amy", message_id=resp["message_id"], action="reject",
        )
        assert rejection["approval_status"] == "rejected"

        # Rejection system message exists
        msgs, _ = queries.get_conversation_messages(db, req["conversation_id"])
        system_msgs = [m for m in msgs if m["from_user"] == "system"]
        rejection_msgs = [m for m in system_msgs if "rejected" in m["body"].lower()]
        assert len(rejection_msgs) >= 1

    def test_cross_domain_expert_search(self, db, seeded_profiles):
        """Search for tags that span multiple domains."""
        # "compliance" exists in both HR (amy) and Finance (bob)
        result = tool_find_experts(db, user_id="keith", tags=["compliance", "budgeting"])
        # Bob should rank higher (2 matches) vs Amy (1 match)
        assert result["experts"][0]["user_id"] == "bob"
        assert result["experts"][0]["match_score"] == 2
        assert result["experts"][1]["user_id"] == "amy"
        assert result["experts"][1]["match_score"] == 1
