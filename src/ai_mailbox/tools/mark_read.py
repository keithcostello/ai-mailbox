"""mark_read tool -- explicitly advance read cursor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import (
    advance_read_cursor,
    get_conversation,
    get_conversation_participants,
    get_last_read_sequence,
    get_max_sequence,
)
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_mark_read(
    db: DBConnection,
    *,
    user_id: str,
    conversation_id: str,
    up_to_sequence: int | None = None,
) -> dict:
    """Explicitly advance read cursor for a conversation."""
    # Validate conversation exists
    conv = get_conversation(db, conversation_id)
    if not conv:
        return make_error("CONVERSATION_NOT_FOUND", "Conversation does not exist")

    # Validate user is participant
    participants = get_conversation_participants(db, conversation_id)
    if user_id not in participants:
        return make_error("PERMISSION_DENIED", "Not a participant in this conversation")

    previous_cursor = get_last_read_sequence(db, conversation_id, user_id)
    max_seq = get_max_sequence(db, conversation_id)

    if up_to_sequence is None:
        target = max_seq
    else:
        # Clamp to actual max (no pre-marking future messages)
        target = min(up_to_sequence, max_seq)

    advance_read_cursor(db, conversation_id, user_id, target)

    # Read back actual value (may not have moved if target < previous)
    actual = get_last_read_sequence(db, conversation_id, user_id)

    return {
        "conversation_id": conversation_id,
        "user": user_id,
        "marked_up_to": actual,
        "previous_cursor": previous_cursor,
    }
