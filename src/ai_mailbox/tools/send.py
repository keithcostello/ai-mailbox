"""send_message tool -- send a new message to a user or group."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.config import MAX_BODY_LENGTH
from ai_mailbox.db.queries import (
    find_or_create_direct_conversation,
    find_or_create_group_by_members,
    get_conversation,
    get_conversation_participants,
    get_user,
    insert_message,
)
from ai_mailbox.errors import is_error, make_error
from ai_mailbox.group_tokens import generate_token, validate_token

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_send_message(
    db: DBConnection,
    *,
    user_id: str,
    to: str | list[str] | None = None,
    body: str,
    project: str = "general",
    subject: str | None = None,
    conversation_id: str | None = None,
    content_type: str = "text/plain",
    idempotency_key: str | None = None,
    group_name: str | None = None,
    group_send_token: str | None = None,
) -> dict:
    """Send a message. Supports direct (to=str), group (to=list), or existing conversation."""
    # --- Validation ---
    if not body.strip():
        return make_error("EMPTY_BODY", "Message body cannot be empty", param="body")

    if len(body) > MAX_BODY_LENGTH:
        return make_error(
            "BODY_TOO_LONG",
            f"Body exceeds {MAX_BODY_LENGTH} characters ({len(body)} given)",
            param="body",
        )

    # --- Route to the right mode ---

    # Mode 3: Existing conversation
    if conversation_id:
        return _send_to_conversation(
            db, user_id=user_id, conversation_id=conversation_id,
            body=body, subject=subject, content_type=content_type,
            idempotency_key=idempotency_key,
            group_send_token=group_send_token,
        )

    if to is None:
        return make_error("MISSING_PARAMETER", "Either 'to' or 'conversation_id' is required")

    # Single string self-send check (before normalization for specific error code)
    if isinstance(to, str) and to == user_id:
        return make_error("SELF_SEND", "Cannot send a message to yourself")

    # Normalize to list
    recipients = to if isinstance(to, list) else [to]

    # Deduplicate and remove sender
    recipients = list(dict.fromkeys(r for r in recipients if r != user_id))

    if not recipients:
        return make_error("MISSING_PARAMETER", "No valid recipients after dedup", param="to")

    # Mode 1: Direct (single recipient)
    if len(recipients) == 1:
        return _send_direct(
            db, user_id=user_id, to=recipients[0], body=body,
            project=project, subject=subject, content_type=content_type,
            idempotency_key=idempotency_key,
        )

    # Mode 2: Group (multiple recipients)
    return _send_group(
        db, user_id=user_id, recipients=recipients, body=body,
        project=project, subject=subject, content_type=content_type,
        idempotency_key=idempotency_key, group_name=group_name,
        group_send_token=group_send_token,
    )


def _send_direct(
    db, *, user_id, to, body, project, subject, content_type, idempotency_key
) -> dict:
    """Send a direct 1:1 message."""
    if user_id == to:
        return make_error("SELF_SEND", "Cannot send a message to yourself")

    if get_user(db, to) is None:
        return make_error("RECIPIENT_NOT_FOUND", f"User '{to}' not found", param="to")

    conv_id = find_or_create_direct_conversation(db, user_id, to, project)
    result = insert_message(
        db, conv_id, user_id, body,
        subject=subject, content_type=content_type,
        idempotency_key=idempotency_key,
    )

    if is_error(result):
        return result

    conv = get_conversation(db, conv_id)
    return {
        "message_id": result["id"],
        "conversation_id": conv_id,
        "from_user": user_id,
        "to_user": to,
        "to_users": [to],
        "project": conv["project"] if conv else project,
    }


def _send_group(
    db, *, user_id, recipients, body, project, subject,
    content_type, idempotency_key, group_name, group_send_token,
) -> dict:
    """Send to a group. Requires group_send_token (confirmation protocol)."""
    # Validate all recipients exist
    for r in recipients:
        if get_user(db, r) is None:
            return make_error("RECIPIENT_NOT_FOUND", f"User '{r}' not found", param="to")

    # Check group size
    total = len(set(recipients)) + 1  # +1 for sender
    from ai_mailbox.config import MAX_GROUP_SIZE
    if total > MAX_GROUP_SIZE:
        return make_error("GROUP_TOO_LARGE", f"Group exceeds {MAX_GROUP_SIZE} participants")

    # Find or create the group
    conv_id, _ = find_or_create_group_by_members(
        db, user_id, recipients, project, name=group_name,
    )

    # Group confirmation gate
    return _group_confirmation_gate(
        db, user_id=user_id, conversation_id=conv_id, body=body,
        subject=subject, content_type=content_type,
        idempotency_key=idempotency_key,
        group_send_token=group_send_token,
    )


def _send_to_conversation(
    db, *, user_id, conversation_id, body, subject,
    content_type, idempotency_key, group_send_token,
) -> dict:
    """Send to an existing conversation by ID."""
    conv = get_conversation(db, conversation_id)
    if not conv:
        return make_error("CONVERSATION_NOT_FOUND", "Conversation does not exist")

    participants = get_conversation_participants(db, conversation_id)
    if user_id not in participants:
        return make_error("PERMISSION_DENIED", "Not a participant in this conversation")

    # Direct conversations: no token needed
    if conv["type"] == "direct":
        result = insert_message(
            db, conversation_id, user_id, body,
            subject=subject, content_type=content_type,
            idempotency_key=idempotency_key,
        )
        if is_error(result):
            return result

        other_users = [p for p in participants if p != user_id]
        return {
            "message_id": result["id"],
            "conversation_id": conversation_id,
            "from_user": user_id,
            "to_user": other_users[0] if other_users else user_id,
            "to_users": other_users,
            "project": conv["project"],
        }

    # Group conversations: require token
    return _group_confirmation_gate(
        db, user_id=user_id, conversation_id=conversation_id, body=body,
        subject=subject, content_type=content_type,
        idempotency_key=idempotency_key,
        group_send_token=group_send_token,
    )


def _group_confirmation_gate(
    db, *, user_id, conversation_id, body, subject,
    content_type, idempotency_key, group_send_token,
) -> dict:
    """Enforce group send confirmation protocol."""
    conv = get_conversation(db, conversation_id)
    participants = get_conversation_participants(db, conversation_id)

    if not group_send_token:
        # Return confirmation payload (NOT an error)
        token = generate_token(conversation_id, body)
        preview = body[:100] + "..." if len(body) > 100 else body
        return {
            "confirmation_required": True,
            "group_send_token": token,
            "group": {
                "conversation_id": conversation_id,
                "name": conv["name"] if conv else None,
                "type": conv["type"] if conv else "team_group",
                "project": conv["project"] if conv else "general",
                "participants": participants,
                "participant_count": len(participants),
            },
            "message_preview": preview,
            "instruction": (
                "Show group details to user and get explicit approval before proceeding. "
                "You MUST confirm TWICE: (1) group selection, (2) message send."
            ),
        }

    # Validate token
    ok, error_code = validate_token(group_send_token, conversation_id, body)
    if not ok:
        return make_error(error_code, f"Group send token validation failed: {error_code}")

    # Token valid -- send the message
    result = insert_message(
        db, conversation_id, user_id, body,
        subject=subject, content_type=content_type,
        idempotency_key=idempotency_key,
    )
    if is_error(result):
        return result

    other_users = [p for p in participants if p != user_id]
    return {
        "message_id": result["id"],
        "conversation_id": conversation_id,
        "from_user": user_id,
        "to_user": other_users[0] if other_users else user_id,
        "to_users": other_users,
        "project": conv["project"] if conv else "general",
    }
