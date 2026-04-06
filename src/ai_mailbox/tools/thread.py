"""get_thread tool -- retrieve full conversation thread with pagination."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.config import THREAD_BODY_DISPLAY_LIMIT, THREAD_DEFAULT_LIMIT
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
    limit: int = THREAD_DEFAULT_LIMIT,
    after_sequence: int = 0,
) -> dict:
    """Get conversation thread from any message in it, with pagination.

    Default returns last 5 messages with a summary of earlier messages.
    Bodies over 2000 chars are truncated — use after_sequence to paginate
    for full history.
    """
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

    # Build summary of earlier messages when paginating
    summary = None
    if has_more or after_sequence > 0:
        # Count total messages in conversation
        all_msgs, _ = get_conversation_messages(db, conv_id, after_sequence=0, limit=10000)
        total = len(all_msgs)
        shown = len(messages)
        earlier = total - shown - after_sequence
        if earlier > 0:
            first_msg = all_msgs[0] if all_msgs else None
            first_info = ""
            if first_msg:
                subj = first_msg.get("subject")
                if subj:
                    first_info = f" First message: {subj}."
                else:
                    body_preview = first_msg.get("body", "")[:100]
                    first_info = f" First message: {body_preview}."
            summary = f"{earlier} earlier messages.{first_info} Participants: {', '.join(participants)}."

    # Enrich messages with backward-compat fields and truncation
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

        # Body truncation for context control
        body = m_dict.get("body", "")
        if len(body) > THREAD_BODY_DISPLAY_LIMIT:
            m_dict["full_length"] = len(body)
            m_dict["body"] = body[:THREAD_BODY_DISPLAY_LIMIT] + "..."
            m_dict["truncated"] = True
        else:
            m_dict["truncated"] = False

        enriched.append(m_dict)

    next_cursor = None
    if has_more and enriched:
        next_cursor = enriched[-1]["sequence_number"]

    result = {
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

    if summary:
        result["summary"] = summary

    return result
