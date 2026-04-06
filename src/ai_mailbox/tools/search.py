"""search_messages tool -- full-text search across conversations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_mailbox.db.queries import search_messages
from ai_mailbox.errors import make_error
from ai_mailbox.rate_limit import MCP_READ_LIMIT, check_rate_limit

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def tool_search_messages(
    db: DBConnection,
    *,
    user_id: str,
    query: str,
    project: str | None = None,
    from_user: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 20,
) -> dict:
    """Search messages across all conversations the user participates in."""
    # Rate limit
    if not check_rate_limit(MCP_READ_LIMIT, "mcp_search", user_id):
        return make_error("RATE_LIMITED", "Too many requests, please wait")

    # Validate query
    if not query or not query.strip():
        return make_error("MISSING_PARAMETER", "query is required", param="query")
    if len(query) > 500:
        return make_error("INVALID_PARAMETER", "query must be 500 characters or fewer", param="query")

    # Validate limit
    if limit < 1 or limit > 100:
        return make_error("INVALID_PARAMETER", "limit must be between 1 and 100", param="limit")

    # Validate since/until if provided
    if since is not None:
        try:
            from datetime import datetime
            datetime.fromisoformat(since.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return make_error("INVALID_PARAMETER", "since must be a valid ISO 8601 timestamp", param="since")

    if until is not None:
        try:
            from datetime import datetime
            datetime.fromisoformat(until.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return make_error("INVALID_PARAMETER", "until must be a valid ISO 8601 timestamp", param="until")

    results = search_messages(
        db, user_id, query.strip(),
        project=project, from_user=from_user,
        since=since, until=until, limit=limit,
    )

    messages = []
    for r in results:
        body = r["body"]
        body_preview = body[:200] + ("..." if len(body) > 200 else "")
        messages.append({
            "id": r["id"],
            "conversation_id": r["conversation_id"],
            "from_user": r["from_user"],
            "subject": r.get("subject"),
            "body": body,
            "body_preview": body_preview,
            "content_type": r.get("content_type", "text/plain"),
            "project": r.get("project"),
            "created_at": r["created_at"],
        })

    return {
        "query": query.strip(),
        "result_count": len(messages),
        "messages": messages,
    }
