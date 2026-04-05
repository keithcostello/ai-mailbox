"""get_thread tool — retrieve full conversation thread."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import get_thread

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_get_thread(
    db: DBConnection,
    *,
    user_id: str,
    message_id: str,
) -> dict:
    """Get full conversation thread from any message in it."""
    thread = get_thread(db, message_id)
    if not thread:
        return {"error": f"Message '{message_id}' not found or empty thread"}

    # Verify user is a participant
    participants = set()
    for msg in thread:
        participants.add(msg["from_user"])
        participants.add(msg["to_user"])

    if user_id not in participants:
        return {"error": "You are not a participant in this thread"}

    return {
        "root_message_id": thread[0]["id"],
        "message_count": len(thread),
        "messages": thread,
    }
