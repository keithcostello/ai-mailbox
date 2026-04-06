"""list_users tool -- return all registered users except the caller."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING

from ai_mailbox.db.queries import get_all_users

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection

ONLINE_THRESHOLD_MINUTES = 5


def _is_online(last_seen: str | None) -> bool:
    """Check if user was seen within the online threshold."""
    if not last_seen:
        return False
    try:
        seen_dt = datetime.fromisoformat(last_seen)
        if seen_dt.tzinfo is None:
            seen_dt = seen_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - seen_dt) < timedelta(minutes=ONLINE_THRESHOLD_MINUTES)
    except (ValueError, TypeError):
        return False


def tool_list_users(
    db: DBConnection,
    *,
    user_id: str,
) -> dict:
    """Return all registered users except the calling user."""
    all_users = get_all_users(db)
    others = []
    for u in all_users:
        if u["id"] == user_id:
            continue
        others.append({
            "id": u["id"],
            "display_name": u["display_name"],
            "user_type": u.get("user_type", "human"),
            "last_seen": u.get("last_seen"),
            "online": _is_online(u.get("last_seen")),
        })
    return {
        "users": others,
        "count": len(others),
        "calling_user": user_id,
    }
