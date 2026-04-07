"""whoami tool -- identity check + unread counts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import get_all_users, get_unread_counts, get_user, get_user_profile_metadata
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_whoami(
    db: DBConnection,
    *,
    user_id: str,
) -> dict:
    """Identity check. Returns user info and unread count per project."""
    user = get_user(db, user_id)
    if user is None:
        return make_error("RECIPIENT_NOT_FOUND", "User not found")

    all_users = get_all_users(db)
    others = [{"id": u["id"], "display_name": u["display_name"]} for u in all_users if u["id"] != user_id]
    unread = get_unread_counts(db, user_id)

    profile = get_user_profile_metadata(db, user_id)

    return {
        "user_id": user["id"],
        "display_name": user["display_name"],
        "user_type": user.get("user_type", "human"),
        "session_mode": user.get("session_mode", "persistent"),
        "last_seen": user.get("last_seen"),
        "profile_metadata": profile,
        "other_users": others,
        "unread_counts": unread,
    }
