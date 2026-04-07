"""approve_ai_response tool -- human approval gate for AI-drafted responses."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import (
    get_conversation_participants,
    get_message,
    insert_system_message,
)
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection

_VALID_ACTIONS = {"approve", "reject"}


def tool_approve_ai_response(
    db: DBConnection,
    *,
    user_id: str,
    message_id: str,
    action: str,
) -> dict:
    """Approve or reject an AI-drafted response. Only the sender's human can approve."""
    if action not in _VALID_ACTIONS:
        return make_error(
            "INVALID_ACTION",
            f"Invalid action '{action}'. Must be 'approve' or 'reject'.",
        )

    msg = get_message(db, message_id)
    if not msg:
        return make_error("MESSAGE_NOT_FOUND", "Message does not exist")

    # Only the message author can approve their own AI's draft
    if msg["from_user"] != user_id:
        return make_error("PERMISSION_DENIED", "Only the message sender can approve or reject their AI's draft")

    # Must be in pending state
    if msg.get("approval_status") != "pending_human_approval":
        return make_error(
            "APPROVAL_NOT_PENDING",
            f"Message approval_status is '{msg.get('approval_status')}', not 'pending_human_approval'",
        )

    # Verify caller is participant
    participants = get_conversation_participants(db, msg["conversation_id"])
    if user_id not in participants:
        return make_error("PERMISSION_DENIED", "Not a participant in this conversation")

    new_status = "approved" if action == "approve" else "rejected"
    db.execute(
        "UPDATE messages SET approval_status = ? WHERE id = ?",
        (new_status, message_id),
    )
    db.commit()

    if action == "reject":
        insert_system_message(
            db, msg["conversation_id"],
            f"AI-drafted response was rejected by {user_id}",
        )

    return {
        "message_id": message_id,
        "conversation_id": msg["conversation_id"],
        "approval_status": new_status,
    }
