"""acknowledge tool -- update message acknowledgment state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import (
    get_conversation_participants,
    get_message,
)
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection

_VALID_STATES = {"received", "processing", "completed", "failed"}

_VALID_TRANSITIONS = {
    "pending": {"received", "processing", "completed", "failed"},
    "received": {"processing", "completed", "failed"},
    "processing": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}


def tool_acknowledge(
    db: DBConnection,
    *,
    user_id: str,
    message_id: str,
    state: str,
) -> dict:
    """Update acknowledgment state on a message. Forward-only transitions."""
    if state not in _VALID_STATES:
        return make_error(
            "INVALID_PARAMETER",
            f"Invalid ack state '{state}'. Must be one of: {', '.join(sorted(_VALID_STATES))}",
            param="state",
        )

    msg = get_message(db, message_id)
    if not msg:
        return make_error("MESSAGE_NOT_FOUND", "Message does not exist")

    participants = get_conversation_participants(db, msg["conversation_id"])
    if user_id not in participants:
        return make_error("PERMISSION_DENIED", "Not a participant in this conversation")

    if msg["from_user"] == user_id:
        return make_error("PERMISSION_DENIED", "Cannot acknowledge your own message")

    current_state = msg.get("ack_state", "pending")
    if state not in _VALID_TRANSITIONS.get(current_state, set()):
        return make_error(
            "INVALID_STATE_TRANSITION",
            f"Cannot transition from '{current_state}' to '{state}'",
        )

    db.execute(
        "UPDATE messages SET ack_state = ? WHERE id = ?",
        (state, message_id),
    )
    db.commit()

    return {
        "message_id": message_id,
        "conversation_id": msg["conversation_id"],
        "ack_state": state,
        "previous_state": current_state,
        "acknowledged_by": user_id,
    }
