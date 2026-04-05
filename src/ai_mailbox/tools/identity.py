"""whoami tool — identity check + unread counts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import get_unread_counts

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_whoami(
    db: DBConnection,
    *,
    user_id: str,
) -> dict:
    """Identity check. Returns user info and unread count per project."""
    row = db.fetchone("SELECT id, display_name FROM users WHERE id = ?", (user_id,))
    if row is None:
        return {"error": "User not found"}

    others = db.fetchall("SELECT id, display_name FROM users WHERE id != ?", (user_id,))
    unread = get_unread_counts(db, user_id=user_id)

    return {
        "user_id": row["id"],
        "display_name": row["display_name"],
        "other_users": [{"id": o["id"], "display_name": o["display_name"]} for o in others],
        "unread_counts": unread,
    }
