"""list_users tool -- return all registered users except the caller."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import get_all_users

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_list_users(
    db: DBConnection,
    *,
    user_id: str,
) -> dict:
    """Return all registered users except the calling user."""
    all_users = get_all_users(db)
    others = [
        {"id": u["id"], "display_name": u["display_name"]}
        for u in all_users
        if u["id"] != user_id
    ]
    return {
        "users": others,
        "count": len(others),
        "calling_user": user_id,
    }
