"""list_participants tool -- return authoritative participant list for a conversation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import (
    get_conversation,
    get_conversation_participants,
    get_user,
)
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_list_participants(
    db: DBConnection,
    *,
    user_id: str,
    conversation_id: str,
) -> dict:
    """Return the current participant list for a conversation."""
    conv = get_conversation(db, conversation_id)
    if not conv:
        return make_error("CONVERSATION_NOT_FOUND", "Conversation does not exist")

    participants = get_conversation_participants(db, conversation_id)
    if user_id not in participants:
        return make_error("PERMISSION_DENIED", "Not a participant in this conversation")

    participant_details = []
    for pid in participants:
        if pid == "system":
            continue
        user = get_user(db, pid)
        if user and user.get("user_type") == "system":
            continue
        participant_details.append({
            "user_id": pid,
            "display_name": user["display_name"] if user else pid,
            "user_type": user.get("user_type", "human") if user else "human",
        })

    return {
        "conversation_id": conversation_id,
        "type": conv["type"],
        "name": conv.get("name"),
        "project": conv.get("project"),
        "participants": participant_details,
        "participant_count": len(participant_details),
    }
