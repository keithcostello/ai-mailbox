"""send_message tool — send a new message or start a thread."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import insert_message

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
    """Send a message to another user. User identity from OAuth token."""
    if not body.strip():
        return {"error": "Message body cannot be empty"}

    if user_id == to:
        return {"error": "Cannot send a message to yourself"}

    # Verify recipient exists
    recipient = db.fetchone("SELECT id FROM users WHERE id = ?", (to,))
    if recipient is None:
        return {"error": f"User '{to}' not found"}

    msg_id = insert_message(
        db, from_user=user_id, to_user=to, body=body,
        project=project, subject=subject,
    )
    return {
        "message_id": msg_id,
        "from_user": user_id,
        "to_user": to,
        "project": project,
    }
