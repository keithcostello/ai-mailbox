"""add_participant tool -- add a user to an existing group conversation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.config import MAX_GROUP_SIZE
from ai_mailbox.db.queries import (
    add_participant,
    get_conversation,
    get_conversation_participants,
    get_user,
)
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_add_participant(
    db: DBConnection,
    *,
    user_id: str,
    conversation_id: str,
    user_to_add: str,
) -> dict:
    """Add a user to a group conversation. Cannot add to direct conversations."""
    conv = get_conversation(db, conversation_id)
    if not conv:
        return make_error("CONVERSATION_NOT_FOUND", "Conversation does not exist")

    # Check caller is participant
    participants = get_conversation_participants(db, conversation_id)
    if user_id not in participants:
        return make_error("PERMISSION_DENIED", "Not a participant in this conversation")

    # Cannot add to direct conversations
    if conv["type"] == "direct":
        return make_error(
            "VALIDATION_ERROR",
            "Cannot add participants to direct conversations",
        )

    # Validate user to add exists
    if get_user(db, user_to_add) is None:
        return make_error("RECIPIENT_NOT_FOUND", f"User '{user_to_add}' not found", param="user_to_add")

    # Check if already member
    if user_to_add in participants:
        return {
            "conversation_id": conversation_id,
            "user_added": user_to_add,
            "already_member": True,
            "participant_count": len(participants),
        }

    # Check size limit
    if len(participants) + 1 > MAX_GROUP_SIZE:
        return make_error("GROUP_TOO_LARGE", f"Group exceeds {MAX_GROUP_SIZE} participants")

    add_participant(db, conversation_id, user_to_add)
    new_participants = get_conversation_participants(db, conversation_id)

    return {
        "conversation_id": conversation_id,
        "user_added": user_to_add,
        "already_member": False,
        "participant_count": len(new_participants),
    }
