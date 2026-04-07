"""check_broadcast_queue tool -- see open broadcasts matching your expertise."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import get_open_broadcasts_for_user
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_check_broadcast_queue(
    db: DBConnection,
    *,
    user_id: str,
    limit: int = 10,
) -> dict:
    """Check the broadcast queue for questions matching your expertise."""
    if limit < 1 or limit > 50:
        return make_error("INVALID_PARAMETER", "limit must be between 1 and 50", param="limit")

    results = get_open_broadcasts_for_user(db, user_id)[:limit]

    return {
        "queue_count": len(results),
        "requests": results,
        "instruction": (
            "Use mailbox_claim_broadcast to claim a request you can help with. "
            "Your human must approve before you spend tokens drafting an answer."
        ) if results else "No matching requests in the queue right now.",
    }
