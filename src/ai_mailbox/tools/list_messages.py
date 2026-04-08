"""list_messages tool -- pure read, no cursor advancement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import (
    get_conversation,
    get_conversation_participants,
    list_messages_query,
)
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_list_messages(
    db: DBConnection,
    *,
    user_id: str,
    project: str | None = None,
    unread_only: bool = True,
    conversation_id: str | None = None,
    limit: int = 50,
    after_sequence: int = 0,
) -> dict:
    """List messages without advancing read cursor. Pure read operation."""
    # Validate parameters
    if limit < 1 or limit > 200:
        return make_error(
            "INVALID_PARAMETER",
            "limit must be between 1 and 200",
            param="limit",
        )
    if after_sequence < 0:
        return make_error(
            "INVALID_PARAMETER",
            "after_sequence must be >= 0",
            param="after_sequence",
        )

    # If conversation_id specified, validate access
    if conversation_id:
        conv = get_conversation(db, conversation_id)
        if not conv:
            return make_error("CONVERSATION_NOT_FOUND", "Conversation does not exist")
        participants = get_conversation_participants(db, conversation_id)
        if user_id not in participants:
            return make_error("PERMISSION_DENIED", "Not a participant in this conversation")

    msgs, has_more = list_messages_query(
        db, user_id,
        project=project,
        unread_only=unread_only,
        conversation_id=conversation_id,
        after_sequence=after_sequence,
        limit=limit,
    )

    # Compute next_cursor
    # In single-conversation mode, cursor is sequence_number (per-conversation).
    # In cross-conversation mode, cursor is offset (after_sequence + page size).
    next_cursor = None
    if has_more and msgs:
        if conversation_id:
            next_cursor = msgs[-1]["sequence_number"]
        else:
            next_cursor = after_sequence + len(msgs)

    # Truncate bodies to previews -- full content via get_thread
    previews = []
    for m in msgs:
        d = dict(m)
        body = d.get("body", "")
        if len(body) > 200:
            d["body"] = body[:200] + "..."
        previews.append(d)

    return {
        "user": user_id,
        "message_count": len(msgs),
        "has_more": has_more,
        "next_cursor": next_cursor,
        "messages": previews,
    }
