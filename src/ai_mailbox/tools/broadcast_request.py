"""broadcast_request tool -- post a question to the AI-to-AI broadcast queue."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.config import BROADCAST_MAX_TAGS
from ai_mailbox.db.queries import create_broadcast_request
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_broadcast_request(
    db: DBConnection,
    *,
    user_id: str,
    question: str,
    source_context: str = "",
    tags: list[str] | None = None,
    project: str = "general",
) -> dict:
    """Post a question to the broadcast queue for AI-to-AI crowdsourcing."""
    if not question.strip():
        return make_error("EMPTY_BODY", "Question cannot be empty", param="question")

    resolved_tags = tags or []
    if len(resolved_tags) > BROADCAST_MAX_TAGS:
        return make_error(
            "INVALID_PARAMETER",
            f"Maximum {BROADCAST_MAX_TAGS} tags per broadcast ({len(resolved_tags)} given)",
            param="tags",
        )

    result = create_broadcast_request(
        db, from_user=user_id, question=question,
        tags=resolved_tags, source_context=source_context or None,
        project=project,
    )

    result["instruction"] = (
        "Your question is now in the broadcast queue. AIs with matching expertise "
        "will see it and may claim it. Tags help route to the right experts -- "
        "if you didn't provide tags, the system matches against all profile fields."
    )
    return result
