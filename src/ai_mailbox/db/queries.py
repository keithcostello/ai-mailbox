"""All SQL operations as named functions.

Works with both SQLite and PostgreSQL via the DBConnection abstraction.
UUIDs and timestamps generated in Python for cross-DB compatibility.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid4())


def insert_message(
    db: DBConnection,
    *,
    from_user: str,
    to_user: str,
    body: str,
    project: str = "general",
    subject: str | None = None,
    reply_to: str | None = None,
) -> str:
    """Insert a message and return its ID."""
    msg_id = _uuid()
    db.execute(
        """INSERT INTO messages (id, from_user, to_user, project, subject, body, reply_to, read, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (msg_id, from_user, to_user, project, subject, body, reply_to, False, _now()),
    )
    db.commit()
    return msg_id


def get_inbox(
    db: DBConnection,
    *,
    user_id: str,
    project: str | None = None,
    unread_only: bool = False,
) -> list[dict]:
    """Get messages for a user's inbox, optionally filtered."""
    conditions = ["to_user = ?"]
    params: list = [user_id]

    if project is not None:
        conditions.append("project = ?")
        params.append(project)

    if unread_only:
        conditions.append("read = ?")
        params.append(False)

    where = " AND ".join(conditions)
    return db.fetchall(
        f"SELECT * FROM messages WHERE {where} ORDER BY created_at ASC",
        tuple(params),
    )


def mark_read(db: DBConnection, message_id: str) -> None:
    """Mark a message as read. Idempotent."""
    db.execute("UPDATE messages SET read = ? WHERE id = ?", (True, message_id))
    db.commit()


def get_message(db: DBConnection, message_id: str) -> dict | None:
    """Get a single message by ID."""
    return db.fetchone("SELECT * FROM messages WHERE id = ?", (message_id,))


def get_thread(db: DBConnection, message_id: str) -> list[dict]:
    """Get full conversation thread from any message in it.

    Walks up to root via reply_to, then collects all descendants.
    Uses iterative approach for SQLite compatibility.
    """
    # Walk up to root
    current_id = message_id
    while True:
        msg = get_message(db, current_id)
        if msg is None:
            return []
        if msg["reply_to"] is None:
            root_id = current_id
            break
        current_id = msg["reply_to"]

    # Collect all messages in thread (BFS from root)
    thread = []
    queue = [root_id]
    visited = set()

    while queue:
        mid = queue.pop(0)
        if mid in visited:
            continue
        visited.add(mid)

        msg = get_message(db, mid)
        if msg:
            thread.append(msg)
            children = db.fetchall(
                "SELECT id FROM messages WHERE reply_to = ? ORDER BY created_at ASC",
                (mid,),
            )
            for child in children:
                queue.append(child["id"])

    thread.sort(key=lambda m: m["created_at"])
    return thread


def get_unread_counts(db: DBConnection, *, user_id: str) -> dict[str, int]:
    """Get unread message count per project for a user."""
    rows = db.fetchall(
        "SELECT project, COUNT(*) as cnt FROM messages WHERE to_user = ? AND read = ? GROUP BY project",
        (user_id, False),
    )
    return {r["project"]: r["cnt"] for r in rows}


