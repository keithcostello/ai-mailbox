"""respond_to_broadcast tool -- handle the full claim lifecycle (Gate 1 + Gate 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import (
    approve_gate1,
    approve_gate2,
    decline_gate1,
    get_broadcast_request,
    reject_gate2,
    submit_draft,
)
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection

_VALID_ACTIONS = {
    "approve_question",  # Gate 1 pass
    "decline_question",  # Gate 1 fail
    "submit_draft",      # Submit answer for Gate 2
    "approve_answer",    # Gate 2 pass
    "reject_answer",     # Gate 2 fail
    "release",           # Give up claim
}


def tool_respond_to_broadcast(
    db: DBConnection,
    *,
    user_id: str,
    broadcast_id: str,
    action: str,
    draft_response: str | None = None,
) -> dict:
    """Handle broadcast claim lifecycle: approve/decline question, submit/approve/reject answer."""
    if action not in _VALID_ACTIONS:
        return make_error(
            "INVALID_BROADCAST_ACTION",
            f"Invalid action '{action}'. Must be one of: {', '.join(sorted(_VALID_ACTIONS))}",
        )

    br = get_broadcast_request(db, broadcast_id)
    if not br:
        return make_error("BROADCAST_NOT_FOUND", "Broadcast request does not exist")

    if action == "approve_question":
        result = approve_gate1(db, broadcast_id, user_id)
        result["instruction"] = (
            "Gate 1 approved. Now draft an answer based on your human's knowledge. "
            "Use action='submit_draft' with draft_response when ready."
        )
        return result

    if action == "decline_question":
        result = decline_gate1(db, broadcast_id, user_id)
        result["instruction"] = "Released back to pool. Other AIs may claim it."
        return result

    if action == "submit_draft":
        if not draft_response or not draft_response.strip():
            return make_error("EMPTY_BODY", "draft_response is required for submit_draft", param="draft_response")
        result = submit_draft(db, broadcast_id, user_id, draft_response)
        result["instruction"] = (
            "Draft submitted for human review (Gate 2). "
            "Show the draft to your human. Use action='approve_answer' or 'reject_answer'."
        )
        return result

    if action == "approve_answer":
        result = approve_gate2(db, broadcast_id, user_id)
        result["instruction"] = "Answer approved and delivered to the requester."
        return result

    if action == "reject_answer":
        result = reject_gate2(db, broadcast_id, user_id)
        result["instruction"] = (
            "Answer rejected. You can submit a new draft with action='submit_draft', "
            "or release the claim with action='release'."
        )
        return result

    if action == "release":
        result = decline_gate1(db, broadcast_id, user_id)
        result["instruction"] = "Claim released. Request is back in the pool."
        return result

    return make_error("INVALID_BROADCAST_ACTION", f"Unhandled action: {action}")
