"""my_claims tool -- view your claimed broadcast requests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import get_my_claims

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_my_claims(
    db: DBConnection,
    *,
    user_id: str,
    status: str | None = None,
) -> dict:
    """View broadcast requests you have claimed and their status."""
    results = get_my_claims(db, user_id, status=status)

    return {
        "claim_count": len(results),
        "claims": [dict(r) for r in results],
        "filter": status,
    }
