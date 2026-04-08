"""AI-to-AI message types, approval gate, and end-to-end flow."""

from __future__ import annotations

import json

import pytest

from ai_mailbox.db import queries
from ai_mailbox.errors import is_error


# ---------------------------------------------------------------------------
# ai-to-ai/request content type validation
# ---------------------------------------------------------------------------

class TestAiToAiRequestValidation:
    """send_message validates ai-to-ai/request body structure."""

    def test_valid_request(self, db):
        from ai_mailbox.tools.send import tool_send_message
        body = json.dumps({
            "question": "How do we handle benefits enrollment?",
            "source_context": "Finance team onboarding project",
            "tags": ["hr", "benefits", "onboarding"],
        })
        result = tool_send_message(
            db, user_id="keith", to="amy", body=body,
            content_type="ai-to-ai/request",
        )
        assert "message_id" in result

    def test_missing_question_field(self, db):
        from ai_mailbox.tools.send import tool_send_message
        body = json.dumps({"source_context": "ctx", "tags": ["hr"]})
        result = tool_send_message(
            db, user_id="keith", to="amy", body=body,
            content_type="ai-to-ai/request",
        )
        assert is_error(result)

    def test_missing_tags_field(self, db):
        from ai_mailbox.tools.send import tool_send_message
        body = json.dumps({"question": "q", "source_context": "ctx"})
        result = tool_send_message(
            db, user_id="keith", to="amy", body=body,
            content_type="ai-to-ai/request",
        )
        assert is_error(result)

    def test_invalid_json_body(self, db):
        from ai_mailbox.tools.send import tool_send_message
        result = tool_send_message(
            db, user_id="keith", to="amy", body="not json",
            content_type="ai-to-ai/request",
        )
        assert is_error(result)

    def test_generates_system_message(self, db):
        from ai_mailbox.tools.send import tool_send_message
        body = json.dumps({
            "question": "HR question",
            "source_context": "finance project",
            "tags": ["hr"],
        })
        result = tool_send_message(
            db, user_id="keith", to="amy", body=body,
            content_type="ai-to-ai/request",
        )
        msgs, _ = queries.get_conversation_messages(db, result["conversation_id"])
        system_msgs = [m for m in msgs if m["from_user"] == "system"]
        assert len(system_msgs) >= 1
        assert "ai-to-ai" in system_msgs[0]["body"].lower() or "request" in system_msgs[0]["body"].lower()


# ---------------------------------------------------------------------------
# ai-to-ai/response content type + approval gate
# ---------------------------------------------------------------------------

class TestAiToAiResponseValidation:
    """send_message validates ai-to-ai/response and sets approval_status."""

    def test_valid_response_with_approval(self, db):
        from ai_mailbox.tools.send import tool_send_message
        body = json.dumps({
            "draft_response": "Benefits enrollment opens in Q2.",
            "requires_human_approval": True,
        })
        result = tool_send_message(
            db, user_id="amy", to="keith", body=body,
            content_type="ai-to-ai/response",
        )
        assert "message_id" in result
        msg = queries.get_message(db, result["message_id"])
        assert msg["approval_status"] == "pending_human_approval"

    def test_response_without_approval_flag(self, db):
        from ai_mailbox.tools.send import tool_send_message
        body = json.dumps({
            "draft_response": "Quick answer.",
            "requires_human_approval": False,
        })
        result = tool_send_message(
            db, user_id="amy", to="keith", body=body,
            content_type="ai-to-ai/response",
        )
        assert "message_id" in result
        msg = queries.get_message(db, result["message_id"])
        assert msg["approval_status"] is None

    def test_missing_draft_response(self, db):
        from ai_mailbox.tools.send import tool_send_message
        body = json.dumps({"requires_human_approval": True})
        result = tool_send_message(
            db, user_id="amy", to="keith", body=body,
            content_type="ai-to-ai/response",
        )
        assert is_error(result)

    def test_invalid_json_response(self, db):
        from ai_mailbox.tools.send import tool_send_message
        result = tool_send_message(
            db, user_id="amy", to="keith", body="not json",
            content_type="ai-to-ai/response",
        )
        assert is_error(result)


# ---------------------------------------------------------------------------
# approve_ai_response tool
# ---------------------------------------------------------------------------

class TestApproveAiResponse:
    """Human approval gate for AI-drafted responses."""

    def _create_pending_message(self, db):
        """Helper: create an ai-to-ai response pending approval."""
        from ai_mailbox.tools.send import tool_send_message
        body = json.dumps({
            "draft_response": "The answer is 42.",
            "requires_human_approval": True,
        })
        return tool_send_message(
            db, user_id="amy", to="keith", body=body,
            content_type="ai-to-ai/response",
        )

    def test_approve(self, db):
        from ai_mailbox.tools.approve_ai_response import tool_approve_ai_response
        send_result = self._create_pending_message(db)
        result = tool_approve_ai_response(
            db, user_id="amy", message_id=send_result["message_id"], action="approve",
        )
        assert result["approval_status"] == "approved"
        msg = queries.get_message(db, send_result["message_id"])
        assert msg["approval_status"] == "approved"

    def test_reject(self, db):
        from ai_mailbox.tools.approve_ai_response import tool_approve_ai_response
        send_result = self._create_pending_message(db)
        result = tool_approve_ai_response(
            db, user_id="amy", message_id=send_result["message_id"], action="reject",
        )
        assert result["approval_status"] == "rejected"

    def test_reject_creates_system_message(self, db):
        from ai_mailbox.tools.approve_ai_response import tool_approve_ai_response
        send_result = self._create_pending_message(db)
        tool_approve_ai_response(
            db, user_id="amy", message_id=send_result["message_id"], action="reject",
        )
        msgs, _ = queries.get_conversation_messages(db, send_result["conversation_id"])
        system_msgs = [m for m in msgs if m["from_user"] == "system"]
        assert any("rejected" in m["body"].lower() for m in system_msgs)

    def test_cannot_approve_non_pending(self, db):
        from ai_mailbox.tools.approve_ai_response import tool_approve_ai_response
        # Regular message (no approval_status)
        conv = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        msg_result = queries.insert_message(db, conv, "amy", "regular message")
        result = tool_approve_ai_response(
            db, user_id="amy", message_id=msg_result["id"], action="approve",
        )
        assert is_error(result)
        assert result["error"]["code"] == "APPROVAL_NOT_PENDING"

    def test_only_sender_can_approve(self, db):
        from ai_mailbox.tools.approve_ai_response import tool_approve_ai_response
        send_result = self._create_pending_message(db)
        # keith tries to approve amy's draft -- should fail
        result = tool_approve_ai_response(
            db, user_id="keith", message_id=send_result["message_id"], action="approve",
        )
        assert is_error(result)
        assert result["error"]["code"] == "PERMISSION_DENIED"

    def test_invalid_action(self, db):
        from ai_mailbox.tools.approve_ai_response import tool_approve_ai_response
        send_result = self._create_pending_message(db)
        result = tool_approve_ai_response(
            db, user_id="amy", message_id=send_result["message_id"], action="maybe",
        )
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_ACTION"

    def test_message_not_found(self, db):
        from ai_mailbox.tools.approve_ai_response import tool_approve_ai_response
        result = tool_approve_ai_response(
            db, user_id="amy", message_id="fake-id", action="approve",
        )
        assert is_error(result)

    def test_double_approve_fails(self, db):
        from ai_mailbox.tools.approve_ai_response import tool_approve_ai_response
        send_result = self._create_pending_message(db)
        tool_approve_ai_response(
            db, user_id="amy", message_id=send_result["message_id"], action="approve",
        )
        result = tool_approve_ai_response(
            db, user_id="amy", message_id=send_result["message_id"], action="approve",
        )
        assert is_error(result)
        assert result["error"]["code"] == "APPROVAL_NOT_PENDING"


# ---------------------------------------------------------------------------
# End-to-end flow
# ---------------------------------------------------------------------------

class TestAiToAiEndToEnd:
    """Full flow: find_experts -> send request -> draft response -> approve."""

    def test_full_flow(self, db):
        from ai_mailbox.db.queries import update_user_profile_metadata
        from ai_mailbox.tools.find_experts import tool_find_experts
        from ai_mailbox.tools.send import tool_send_message
        from ai_mailbox.tools.approve_ai_response import tool_approve_ai_response

        # Step 1: Amy has HR expertise
        update_user_profile_metadata(db, "amy", {
            "expertise_tags": ["hr", "onboarding"],
            "bio": "HR specialist AI",
        })

        # Step 2: Keith finds experts
        experts = tool_find_experts(db, user_id="keith", tags=["hr", "onboarding"])
        assert experts["result_count"] == 1
        assert experts["experts"][0]["user_id"] == "amy"

        # Step 3: Keith sends ai-to-ai request
        request_body = json.dumps({
            "question": "What is the benefits enrollment process?",
            "source_context": "Finance team Q2 planning",
            "tags": ["hr", "benefits"],
        })
        req = tool_send_message(
            db, user_id="keith", to="amy", body=request_body,
            content_type="ai-to-ai/request",
        )
        assert "message_id" in req

        # Step 4: Amy's AI drafts a response (requires approval)
        response_body = json.dumps({
            "draft_response": "Benefits enrollment opens March 15. Contact HR portal for options.",
            "requires_human_approval": True,
        })
        resp = tool_send_message(
            db, user_id="amy", to="keith", body=response_body,
            content_type="ai-to-ai/response",
        )
        assert "message_id" in resp
        msg = queries.get_message(db, resp["message_id"])
        assert msg["approval_status"] == "pending_human_approval"

        # Step 5: Amy (human) approves
        approval = tool_approve_ai_response(
            db, user_id="amy", message_id=resp["message_id"], action="approve",
        )
        assert approval["approval_status"] == "approved"

        # Step 6: Verify thread has all messages
        msgs, _ = queries.get_conversation_messages(db, req["conversation_id"])
        content_types = [m.get("content_type") for m in msgs]
        assert "ai-to-ai/request" in content_types
        assert "ai-to-ai/response" in content_types
