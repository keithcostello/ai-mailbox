"""get_thread tool -- retrieve full conversation thread with pagination."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import (
    get_conversation,
    get_conversation_messages,
    get_conversation_participants,
    get_message,
)
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_get_thread(
    db: DBConnection,
    *,
    user_id: str,
    message_id: str,
    limit: int = 100,
    after_sequence: int = 0,
) -> dict:
    """Get conversation thread from any message in it, with pagination."""
    if limit < 1 or limit > 200:
        return make_error("INVALID_PARAMETER", "limit must be between 1 and 200", param="limit")

    msg = get_message(db, message_id)
    if msg is None:
        return make_error("MESSAGE_NOT_FOUND", f"Message '{message_id}' not found", param="message_id")

    conv_id = msg["conversation_id"]
    participants = get_conversation_participants(db, conv_id)

    if user_id not in participants:
        return make_error("PERMISSION_DENIED", "You are not a participant in this conversation")

    messages, has_more = get_conversation_messages(
        db, conv_id, after_sequence=after_sequence, limit=limit,
    )
    conv = get_conversation(db, conv_id)

    # Enrich messages with backward-compat fields
    other_users = [p for p in participants if p != user_id]
    enriched = []
    for m in messages:
        m_dict = dict(m)
        if m["from_user"] == user_id and other_users:
            m_dict["to_user"] = other_users[0]
        elif m["from_user"] != user_id:
            m_dict["to_user"] = user_id
        else:
            m_dict["to_user"] = m["from_user"]
        m_dict["project"] = conv["project"] if conv else None
        enriched.append(m_dict)

    next_cursor = None
    if has_more and enriched:
        next_cursor = enriched[-1]["sequence_number"]

    return {
        "conversation": {
            "id": conv_id,
            "type": conv["type"] if conv else None,
            "project": conv["project"] if conv else None,
            "name": conv["name"] if conv else None,
            "participants": participants,
        },
        "root_message_id": enriched[0]["id"] if enriched else None,
        "message_count": len(enriched),
        "has_more": has_more,
        "next_cursor": next_cursor,
        "messages": enriched,
    }
