"""send_message tool -- send a new message to another user."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import (
    find_or_create_direct_conversation,
    get_conversation,
    get_user,
    insert_message,
)
from ai_mailbox.errors import is_error, make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_send_message(
    db: DBConnection,
    *,
    user_id: str,
    to: str,
    body: str,
    project: str = "general",
    subject: str | None = None,
) -> dict:
    """Send a message to another user."""
    if not body.strip():
        return make_error("EMPTY_BODY", "Message body cannot be empty", param="body")

    if user_id == to:
        return make_error("SELF_SEND", "Cannot send a message to yourself")

    if get_user(db, to) is None:
        return make_error("RECIPIENT_NOT_FOUND", f"User '{to}' not found", param="to")

    conv_id = find_or_create_direct_conversation(db, user_id, to, project)
    result = insert_message(db, conv_id, user_id, body, subject=subject)

    if is_error(result):
        return result

    conv = get_conversation(db, conv_id)
    return {
        "message_id": result["id"],
        "from_user": user_id,
        "to_user": to,
        "project": conv["project"] if conv else project,
    }
