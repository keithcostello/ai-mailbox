"""check_messages tool -- check inbox, optionally filtered by project."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import (
    advance_read_cursor,
    get_conversation,
    get_conversation_messages,
    get_conversation_participants,
    get_inbox,
    get_last_read_sequence,
)

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_check_messages(
    db: DBConnection,
    *,
    user_id: str,
    project: str | None = None,
    unread_only: bool = True,
) -> dict:
    """Check inbox. Returns messages and advances read cursor (backward compat)."""
    inbox_entries = get_inbox(db, user_id, project=project)

    all_messages = []
    for entry in inbox_entries:
        conv_id = entry["conversation_id"]
        last_read = get_last_read_sequence(db, conv_id, user_id)
        conv = get_conversation(db, conv_id)
        participants = get_conversation_participants(db, conv_id)
        other_users = [p for p in participants if p != user_id]

        if unread_only:
            msgs, _ = get_conversation_messages(db, conv_id, after_sequence=last_read)
        else:
            msgs, _ = get_conversation_messages(db, conv_id)

        # Enrich messages with backward-compat fields
        max_seq = last_read
        for msg in msgs:
            to_user = other_users[0] if other_users else user_id
            if msg["from_user"] == user_id and other_users:
                to_user = other_users[0]
            elif msg["from_user"] != user_id:
                to_user = user_id
            msg_dict = dict(msg)
            msg_dict["to_user"] = to_user
            msg_dict["project"] = conv["project"] if conv else None
            all_messages.append(msg_dict)
            if msg["sequence_number"] > max_seq:
                max_seq = msg["sequence_number"]

        # Auto-advance read cursor (backward compat, replaced by explicit mark_read in Sprint 2)
        if max_seq > last_read:
            advance_read_cursor(db, conv_id, user_id, max_seq)

    # Sort by created_at
    all_messages.sort(key=lambda m: m["created_at"])

    return {
        "user": user_id,
        "message_count": len(all_messages),
        "messages": all_messages,
    }
