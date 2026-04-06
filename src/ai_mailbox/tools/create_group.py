"""create_group tool -- create a named team group conversation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.config import MAX_GROUP_SIZE
from ai_mailbox.db.queries import (
    get_conversation,
    get_conversation_participants,
    get_user,
    find_or_create_group_by_members,
)
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_create_group(
    db: DBConnection,
    *,
    user_id: str,
    name: str,
    members: list[str],
    project: str = "general",
) -> dict:
    """Create a named team group. Idempotent by name+project+creator."""
    if not name or not name.strip():
        return make_error("VALIDATION_ERROR", "Group name cannot be empty", param="name")

    if len(name) > 256:
        return make_error("VALIDATION_ERROR", "Group name exceeds 256 characters", param="name")

    if not members:
        return make_error("VALIDATION_ERROR", "Members list cannot be empty", param="members")

    # Validate all members exist
    for m in members:
        if get_user(db, m) is None:
            return make_error("RECIPIENT_NOT_FOUND", f"User '{m}' not found", param="members")

    # Check group size
    all_members = set(members) | {user_id}
    if len(all_members) > MAX_GROUP_SIZE:
        return make_error("GROUP_TOO_LARGE", f"Group exceeds {MAX_GROUP_SIZE} participants")

    # Try to find existing group with same name + project
    # (find_or_create_group_by_members uses auto-name; for explicit names,
    # check manually first)
    from ai_mailbox.db.queries import _uuid, _now, create_team_group
    from ai_mailbox.db.queries import get_conversation as _get_conv

    # Check for existing group with this name by the same creator in this project
    row = db.fetchone(
        "SELECT id FROM conversations WHERE type = 'team_group' AND project = ? AND name = ?",
        (project, name),
    )
    if row:
        conv_id = row["id"]
        participants = get_conversation_participants(db, conv_id)
        return {
            "conversation_id": conv_id,
            "name": name,
            "project": project,
            "participants": sorted(participants),
            "created": False,
        }

    # Create new
    conv_id = create_team_group(db, name, user_id, list(members), project=project)
    participants = get_conversation_participants(db, conv_id)

    return {
        "conversation_id": conv_id,
        "name": name,
        "project": project,
        "participants": sorted(participants),
        "created": True,
    }
