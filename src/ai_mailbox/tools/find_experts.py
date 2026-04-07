"""find_experts tool -- directory lookup for AI-to-AI routing by expertise tags."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.config import MAX_FIND_EXPERTS_TAGS
from ai_mailbox.db.queries import find_experts_by_tags
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_find_experts(
    db: DBConnection,
    *,
    user_id: str,
    tags: list[str],
    limit: int = 10,
) -> dict:
    """Find users whose expertise matches the given tags."""
    if not tags:
        return make_error("INVALID_PARAMETER", "tags must be a non-empty list", param="tags")

    if len(tags) > MAX_FIND_EXPERTS_TAGS:
        return make_error(
            "INVALID_PARAMETER",
            f"Maximum {MAX_FIND_EXPERTS_TAGS} tags per query ({len(tags)} given)",
            param="tags",
        )

    if not all(isinstance(t, str) and t.strip() for t in tags):
        return make_error("INVALID_PARAMETER", "Each tag must be a non-empty string", param="tags")

    if any(len(t) > 100 for t in tags):
        return make_error("INVALID_PARAMETER", "Each tag must be 100 characters or fewer", param="tags")

    if limit < 1 or limit > 50:
        return make_error("INVALID_PARAMETER", "limit must be between 1 and 50", param="limit")

    results = find_experts_by_tags(db, tags, limit=limit, exclude_user=user_id)

    return {
        "query_tags": tags,
        "result_count": len(results),
        "experts": results,
        "instruction": (
            "Use send_message with content_type='ai-to-ai/request' to contact an expert. "
            "Include a structured JSON body with 'question', 'source_context', and 'tags' fields."
        ),
    }
