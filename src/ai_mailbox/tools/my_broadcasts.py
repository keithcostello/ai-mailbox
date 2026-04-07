"""my_broadcasts tool -- view your active and past broadcast requests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import get_my_broadcasts
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection

_VALID_STATUSES = {"open", "claimed", "drafting", "pending_review", "fulfilled", "expired", "cancelled"}


def tool_my_broadcasts(
    db: DBConnection,
    *,
    user_id: str,
    status: str | None = None,
) -> dict:
    """View your broadcast requests and their status."""
    if status and status not in _VALID_STATUSES:
        return make_error(
            "INVALID_PARAMETER",
            f"Invalid status filter '{status}'. Must be one of: {', '.join(sorted(_VALID_STATUSES))}",
            param="status",
        )

    results = get_my_broadcasts(db, user_id, status=status)

    return {
        "broadcast_count": len(results),
        "broadcasts": [dict(r) for r in results],
        "filter": status,
    }
