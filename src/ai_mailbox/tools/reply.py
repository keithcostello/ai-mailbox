"""reply_to_message tool — reply to a specific message."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import get_message, insert_message

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_reply_to_message(
    db: DBConnection,
    *,
    user_id: str,
    message_id: str,
    body: str,
) -> dict:
    """Reply to a message. Inherits project from the original. Swaps from/to."""
    original = get_message(db, message_id)
    if original is None:
        return {"error": f"Message '{message_id}' not found"}

    # Only the recipient can reply
    if original["to_user"] != user_id:
        return {"error": "You can only reply to messages addressed to you"}

    reply_id = insert_message(
        db,
        from_user=user_id,
        to_user=original["from_user"],
        body=body,
        project=original["project"],
        subject=original.get("subject"),
        reply_to=message_id,
    )
    return {
        "message_id": reply_id,
        "from_user": user_id,
        "to_user": original["from_user"],
        "project": original["project"],
    }
