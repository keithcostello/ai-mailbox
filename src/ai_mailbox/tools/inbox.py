"""check_messages tool — check inbox, optionally filtered by project."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import get_inbox, mark_read

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_check_messages(
    db: DBConnection,
    *,
    user_id: str,
    project: str | None = None,
    unread_only: bool = True,
) -> dict:
    """Check inbox. Marks returned unread messages as read."""
    messages = get_inbox(db, user_id=user_id, project=project, unread_only=unread_only)

    # Mark unread messages as read
    for msg in messages:
        if not msg["read"]:
            mark_read(db, msg["id"])

    return {
        "user": user_id,
        "message_count": len(messages),
        "messages": messages,
    }
