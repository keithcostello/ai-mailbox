"""reply_to_message tool -- reply to a specific message."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import (
    get_conversation,
    get_conversation_participants,
    get_message,
    insert_message,
)
from ai_mailbox.errors import is_error, make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_reply_to_message(
    db: DBConnection,
    *,
    user_id: str,
    message_id: str,
    body: str,
) -> dict:
    """Reply to a message. Any participant in the conversation can reply."""
    if not body.strip():
        return make_error("EMPTY_BODY", "Message body cannot be empty", param="body")

    original = get_message(db, message_id)
    if original is None:
        return make_error("MESSAGE_NOT_FOUND", f"Message '{message_id}' not found", param="message_id")

    conv_id = original["conversation_id"]
    participants = get_conversation_participants(db, conv_id)

    if user_id not in participants:
        return make_error("PERMISSION_DENIED", "You are not a participant in this conversation")

    conv = get_conversation(db, conv_id)
    result = insert_message(
        db, conv_id, user_id, body,
        subject=original.get("subject"),
        reply_to=message_id,
    )

    if is_error(result):
        return result

    # Determine to_user for backward compat response
    other_users = [p for p in participants if p != user_id]
    to_user = other_users[0] if other_users else original["from_user"]

    return {
        "message_id": result["id"],
        "from_user": user_id,
        "to_user": to_user,
        "project": conv["project"] if conv else "general",
    }
