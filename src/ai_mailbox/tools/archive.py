"""archive_conversation tool -- per-user conversation archiving."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import (
    get_conversation,
    get_conversation_participants,
    set_archive,
)
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_archive_conversation(
    db: DBConnection,
    *,
    user_id: str,
    conversation_id: str,
    archive: bool = True,
) -> dict:
    """Archive or unarchive a conversation for the calling user."""
    conv = get_conversation(db, conversation_id)
    if not conv:
        return make_error("CONVERSATION_NOT_FOUND", "Conversation does not exist")

    participants = get_conversation_participants(db, conversation_id)
    if user_id not in participants:
        return make_error("PERMISSION_DENIED", "Not a participant in this conversation")

    archived_at = set_archive(db, conversation_id, user_id, archive)

    return {
        "conversation_id": conversation_id,
        "archived": archive,
        "archived_at": archived_at,
    }
