"""claim_broadcast tool -- claim a broadcast request from the queue."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import claim_broadcast, get_broadcast_request
from ai_mailbox.errors import is_error, make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_claim_broadcast(
    db: DBConnection,
    *,
    user_id: str,
    broadcast_id: str,
) -> dict:
    """Claim a broadcast request. Gate 1 starts -- show question to human, do NOT draft an answer yet."""
    br = get_broadcast_request(db, broadcast_id)
    if not br:
        return make_error("BROADCAST_NOT_FOUND", "Broadcast request does not exist")

    if br["from_user"] == user_id:
        return make_error("INVALID_BROADCAST_ACTION", "Cannot claim your own broadcast request")

    result = claim_broadcast(db, broadcast_id, user_id)
    if is_error(result):
        return result

    result["instruction"] = (
        "IMPORTANT: Show this question to your human and ask if they can help. "
        "Do NOT generate an answer yet -- no tokens should be spent until the human approves. "
        "Use mailbox_respond_to_broadcast with action='approve_question' or 'decline_question'."
    )
    return result
