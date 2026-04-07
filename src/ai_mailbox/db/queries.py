"""Conversation-based query layer for AI Mailbox.

Three-table model: conversations, conversation_participants, messages.
Works with both SQLite and PostgreSQL via the DBConnection abstraction.
UUIDs and timestamps generated in Python for cross-DB compatibility.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from ai_mailbox.config import DEAD_LETTER_THRESHOLD_HOURS
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid4())


# ---------------------------------------------------------------------------
# Conversation management
# ---------------------------------------------------------------------------

def find_or_create_direct_conversation(
    db: DBConnection, user_a: str, user_b: str, project: str
) -> str:
    """Find existing direct conversation between two users in a project, or create one.

    User order does not matter -- (keith, amy) and (amy, keith) find the same conversation.
    Returns conversation_id.
    """
    # Normalize user pair for consistent lookup
    u1, u2 = sorted([user_a, user_b])

    # Try to find existing
    row = db.fetchone(
        """SELECT c.id FROM conversations c
           JOIN conversation_participants cp1 ON c.id = cp1.conversation_id AND cp1.user_id = ?
           JOIN conversation_participants cp2 ON c.id = cp2.conversation_id AND cp2.user_id = ?
           WHERE c.type = 'direct' AND c.project = ?""",
        (u1, u2, project),
    )
    if row:
        return row["id"]

    # Create new conversation
    conv_id = _uuid()
    now = _now()
    db.execute(
        """INSERT INTO conversations (id, type, project, created_by, created_at, updated_at)
           VALUES (?, 'direct', ?, ?, ?, ?)""",
        (conv_id, project, user_a, now, now),
    )
    # Add both participants
    db.execute(
        "INSERT INTO conversation_participants (conversation_id, user_id, joined_at) VALUES (?, ?, ?)",
        (conv_id, u1, now),
    )
    db.execute(
        "INSERT INTO conversation_participants (conversation_id, user_id, joined_at) VALUES (?, ?, ?)",
        (conv_id, u2, now),
    )
    db.commit()
    return conv_id


def find_or_create_project_group(
    db: DBConnection, project: str, created_by: str
) -> str:
    """Find existing project group or create one. Returns conversation_id."""
    row = db.fetchone(
        "SELECT id FROM conversations WHERE type = 'project_group' AND project = ?",
        (project,),
    )
    if row:
        return row["id"]

    conv_id = _uuid()
    now = _now()
    db.execute(
        """INSERT INTO conversations (id, type, project, name, created_by, created_at, updated_at)
           VALUES (?, 'project_group', ?, ?, ?, ?, ?)""",
        (conv_id, project, project, created_by, now, now),
    )
    db.execute(
        "INSERT INTO conversation_participants (conversation_id, user_id, joined_at) VALUES (?, ?, ?)",
        (conv_id, created_by, now),
    )
    db.commit()
    return conv_id


def create_team_group(
    db: DBConnection, name: str, created_by: str, member_ids: list[str],
    project: str | None = None,
) -> str:
    """Create a new team group. Returns conversation_id."""
    conv_id = _uuid()
    now = _now()
    db.execute(
        """INSERT INTO conversations (id, type, project, name, created_by, created_at, updated_at)
           VALUES (?, 'team_group', ?, ?, ?, ?, ?)""",
        (conv_id, project, name, created_by, now, now),
    )
    all_members = set(member_ids) | {created_by}
    for uid in all_members:
        db.execute(
            "INSERT INTO conversation_participants (conversation_id, user_id, joined_at) VALUES (?, ?, ?)",
            (conv_id, uid, now),
        )
    db.commit()
    return conv_id


def find_or_create_group_by_members(
    db: DBConnection,
    creator: str,
    member_ids: list[str],
    project: str,
    name: str | None = None,
) -> tuple[str, bool]:
    """Find existing team_group with exact member set or create one.

    Returns (conversation_id, created: bool).
    Auto-generates name from sorted participant list if name is None.
    """
    all_members = sorted(set(member_ids) | {creator})
    auto_name = ",".join(all_members)
    lookup_name = name if name else auto_name

    # Try to find existing group by name + project
    row = db.fetchone(
        "SELECT id FROM conversations WHERE type = 'team_group' AND project = ? AND name = ?",
        (project, lookup_name),
    )
    if row:
        return row["id"], False

    # Create new group
    conv_id = create_team_group(db, lookup_name, creator, member_ids, project=project)
    return conv_id, True


def add_participant(db: DBConnection, conversation_id: str, user_id: str) -> None:
    """Add a user to a conversation. Idempotent."""
    try:
        db.execute(
            "INSERT INTO conversation_participants (conversation_id, user_id, joined_at) VALUES (?, ?, ?)",
            (conversation_id, user_id, _now()),
        )
        db.commit()
    except (sqlite3.IntegrityError, Exception) as e:
        # Idempotent: ignore if already a participant
        err = str(e).lower()
        if "unique" in err or "duplicate" in err or "primary key" in err:
            return
        raise


def get_conversation(db: DBConnection, conversation_id: str) -> dict | None:
    """Fetch conversation metadata."""
    return db.fetchone("SELECT * FROM conversations WHERE id = ?", (conversation_id,))


def get_conversation_participants(db: DBConnection, conversation_id: str) -> list[str]:
    """Return list of user_ids in a conversation."""
    rows = db.fetchall(
        "SELECT user_id FROM conversation_participants WHERE conversation_id = ? ORDER BY user_id",
        (conversation_id,),
    )
    return [r["user_id"] for r in rows]


# ---------------------------------------------------------------------------
# Archiving
# ---------------------------------------------------------------------------

def set_archive(
    db: DBConnection, conversation_id: str, user_id: str, archive: bool
) -> str | None:
    """Set or clear archived_at for a user in a conversation. Returns archived_at value."""
    if archive:
        now = _now()
        db.execute(
            """UPDATE conversation_participants SET archived_at = ?
               WHERE conversation_id = ? AND user_id = ? AND archived_at IS NULL""",
            (now, conversation_id, user_id),
        )
        db.commit()
        row = db.fetchone(
            "SELECT archived_at FROM conversation_participants WHERE conversation_id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
        return row["archived_at"] if row else now
    else:
        db.execute(
            "UPDATE conversation_participants SET archived_at = NULL WHERE conversation_id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
        db.commit()
        return None


# ---------------------------------------------------------------------------
# Message operations
# ---------------------------------------------------------------------------

def insert_message(
    db: DBConnection,
    conversation_id: str,
    from_user: str,
    body: str,
    *,
    subject: str | None = None,
    reply_to: str | None = None,
    idempotency_key: str | None = None,
    content_type: str = "text/plain",
) -> dict:
    """Insert message, assign sequence number. Returns {id, sequence_number} or error dict."""
    msg_id = _uuid()
    now = _now()

    # Get next sequence number
    row = db.fetchone(
        "SELECT COALESCE(MAX(sequence_number), 0) + 1 AS next_seq FROM messages WHERE conversation_id = ?",
        (conversation_id,),
    )
    next_seq = row["next_seq"]

    try:
        db.execute(
            """INSERT INTO messages (id, conversation_id, from_user, sequence_number,
                                     subject, body, content_type, idempotency_key, reply_to, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, conversation_id, from_user, next_seq, subject, body,
             content_type, idempotency_key, reply_to, now),
        )
    except (sqlite3.IntegrityError, Exception) as e:
        err = str(e).lower()
        if idempotency_key and ("unique" in err or "duplicate" in err):
            return make_error("DUPLICATE_MESSAGE", f"Idempotency key '{idempotency_key}' already used")
        raise

    # Update conversation.updated_at
    db.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (now, conversation_id),
    )
    # Auto-unarchive for recipients (not the sender)
    db.execute(
        """UPDATE conversation_participants
           SET archived_at = NULL
           WHERE conversation_id = ? AND user_id != ? AND archived_at IS NOT NULL""",
        (conversation_id, from_user),
    )
    db.commit()
    return {"id": msg_id, "sequence_number": next_seq}


def insert_system_message(
    db: DBConnection,
    conversation_id: str,
    body: str,
    *,
    content_type: str = "text/plain",
) -> dict:
    """Insert a system-generated message. Bypasses participant checks.

    Returns {id, sequence_number}.
    """
    return insert_message(
        db, conversation_id, "system", body,
        content_type=content_type,
    )


def get_message(db: DBConnection, message_id: str) -> dict | None:
    """Fetch single message by ID."""
    return db.fetchone("SELECT * FROM messages WHERE id = ?", (message_id,))


def get_conversation_messages(
    db: DBConnection,
    conversation_id: str,
    after_sequence: int = 0,
    limit: int = 100,
) -> tuple[list[dict], bool]:
    """Fetch messages in a conversation after a sequence number.

    Ordered by sequence_number ASC.
    Returns (messages, has_more).
    """
    # Fetch one extra to detect has_more
    rows = db.fetchall(
        """SELECT * FROM messages
           WHERE conversation_id = ? AND sequence_number > ?
           ORDER BY sequence_number ASC
           LIMIT ?""",
        (conversation_id, after_sequence, limit + 1),
    )
    has_more = len(rows) > limit
    return rows[:limit], has_more


# ---------------------------------------------------------------------------
# Read tracking
# ---------------------------------------------------------------------------

def get_last_read_sequence(db: DBConnection, conversation_id: str, user_id: str) -> int:
    """Get user's read cursor for a conversation."""
    row = db.fetchone(
        "SELECT last_read_sequence FROM conversation_participants WHERE conversation_id = ? AND user_id = ?",
        (conversation_id, user_id),
    )
    return row["last_read_sequence"] if row else 0


def get_max_sequence(db: DBConnection, conversation_id: str) -> int:
    """Return the highest sequence_number in a conversation. 0 if no messages."""
    row = db.fetchone(
        "SELECT COALESCE(MAX(sequence_number), 0) AS max_seq FROM messages WHERE conversation_id = ?",
        (conversation_id,),
    )
    return row["max_seq"]


def advance_read_cursor(db: DBConnection, conversation_id: str, user_id: str, sequence: int) -> None:
    """Advance user's read cursor. Only moves forward, never backward."""
    # Use CASE expression for cross-DB compat (SQLite has no GREATEST, Postgres MAX is aggregate-only)
    db.execute(
        """UPDATE conversation_participants
           SET last_read_sequence = CASE
               WHEN last_read_sequence < ? THEN ?
               ELSE last_read_sequence
           END
           WHERE conversation_id = ? AND user_id = ?""",
        (sequence, sequence, conversation_id, user_id),
    )
    db.commit()


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------

def get_inbox(
    db: DBConnection, user_id: str, project: str | None = None,
    include_archived: bool = False,
) -> list[dict]:
    """Return conversations for a user with unread counts and last message preview.

    Ordered by last_message_at DESC (most recent first).
    Excludes archived conversations unless include_archived is True.
    """
    conditions = ["cp.user_id = ?"]
    params: list = [user_id]

    if project is not None:
        conditions.append("c.project = ?")
        params.append(project)

    if not include_archived:
        conditions.append("cp.archived_at IS NULL")

    where = " AND ".join(conditions)

    rows = db.fetchall(
        f"""SELECT
                c.id AS conversation_id,
                c.type,
                c.project,
                c.name,
                c.updated_at AS last_message_at,
                cp.last_read_sequence,
                cp.archived_at,
                (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS total_messages,
                (SELECT COUNT(*) FROM messages m
                 WHERE m.conversation_id = c.id AND m.sequence_number > cp.last_read_sequence) AS unread_count,
                (SELECT m.body FROM messages m
                 WHERE m.conversation_id = c.id
                 ORDER BY m.sequence_number DESC LIMIT 1) AS last_message_preview,
                (SELECT m.from_user FROM messages m
                 WHERE m.conversation_id = c.id
                 ORDER BY m.sequence_number DESC LIMIT 1) AS last_message_from
            FROM conversations c
            JOIN conversation_participants cp ON c.id = cp.conversation_id
            WHERE {where}
            ORDER BY c.updated_at DESC""",
        tuple(params),
    )

    result = []
    for r in rows:
        # Only include conversations that have messages
        if r["total_messages"] == 0:
            continue
        participants = get_conversation_participants(db, r["conversation_id"])
        preview = r["last_message_preview"] or ""
        if len(preview) > 100:
            preview = preview[:100] + "..."
        result.append({
            "conversation_id": r["conversation_id"],
            "type": r["type"],
            "project": r["project"],
            "name": r["name"],
            "participants": participants,
            "last_message_preview": preview,
            "last_message_at": r["last_message_at"],
            "last_message_from": r["last_message_from"],
            "unread_count": r["unread_count"],
            "total_messages": r["total_messages"],
            "archived": r["archived_at"] is not None,
        })
    return result


def get_inbox_paginated(
    db: DBConnection,
    user_id: str,
    project: str | None = None,
    limit: int = 50,
    offset: int = 0,
    include_archived: bool = False,
) -> tuple[list[dict], bool]:
    """Paginated inbox. Returns (conversations, has_more)."""
    # Reuse get_inbox, then paginate in Python (fine for alpha scale)
    all_convos = get_inbox(db, user_id, project, include_archived=include_archived)
    page = all_convos[offset : offset + limit + 1]
    has_more = len(page) > limit
    return page[:limit], has_more


def list_messages_query(
    db: DBConnection,
    user_id: str,
    project: str | None = None,
    unread_only: bool = True,
    conversation_id: str | None = None,
    after_sequence: int = 0,
    limit: int = 50,
) -> tuple[list[dict], bool]:
    """Fetch messages for the list_messages tool.

    If conversation_id is specified: messages from that conversation only,
    paginated by after_sequence.
    If not: messages across all user's conversations.
    Returns (messages, has_more).
    """
    if conversation_id:
        # Single conversation mode
        conditions = ["m.conversation_id = ?", "m.sequence_number > ?"]
        params: list = [conversation_id, after_sequence]
        if unread_only:
            conditions.append(
                "m.sequence_number > (SELECT cp.last_read_sequence "
                "FROM conversation_participants cp "
                "WHERE cp.conversation_id = m.conversation_id AND cp.user_id = ?)"
            )
            params.append(user_id)
        where = " AND ".join(conditions)
        rows = db.fetchall(
            f"""SELECT m.* FROM messages m
                WHERE {where}
                ORDER BY m.sequence_number ASC
                LIMIT ?""",
            tuple(params + [limit + 1]),
        )
    else:
        # Cross-conversation mode
        conditions = ["cp.user_id = ?"]
        params = [user_id]
        if project:
            conditions.append("c.project = ?")
            params.append(project)
        if unread_only:
            conditions.append("m.sequence_number > cp.last_read_sequence")
        where = " AND ".join(conditions)
        rows = db.fetchall(
            f"""SELECT m.* FROM messages m
                JOIN conversations c ON m.conversation_id = c.id
                JOIN conversation_participants cp ON c.id = cp.conversation_id
                WHERE {where}
                ORDER BY m.created_at ASC
                LIMIT ?""",
            tuple(params + [limit + 1]),
        )

    has_more = len(rows) > limit
    return rows[:limit], has_more


def get_unread_counts(db: DBConnection, user_id: str) -> dict[str, int]:
    """Return unread message count per project for a user.

    Computed from: messages.sequence_number > participant.last_read_sequence.
    """
    rows = db.fetchall(
        """SELECT c.project, SUM(
                (SELECT COUNT(*) FROM messages m
                 WHERE m.conversation_id = c.id AND m.sequence_number > cp.last_read_sequence)
           ) AS cnt
           FROM conversations c
           JOIN conversation_participants cp ON c.id = cp.conversation_id
           WHERE cp.user_id = ?
           GROUP BY c.project
           HAVING cnt > 0""",
        (user_id,),
    )
    return {r["project"]: r["cnt"] for r in rows}


# ---------------------------------------------------------------------------
# Thread (conversation-based)
# ---------------------------------------------------------------------------

def get_thread(db: DBConnection, message_id: str) -> list[dict]:
    """Get all messages in the conversation containing message_id.

    Ordered by sequence_number ASC. Returns empty list if message not found.
    """
    msg = get_message(db, message_id)
    if msg is None:
        return []
    msgs, _ = get_conversation_messages(db, msg["conversation_id"])
    return msgs


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_messages(
    db: DBConnection,
    user_id: str,
    query: str,
    *,
    project: str | None = None,
    from_user: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Full-text search across messages the user can see.

    Uses PostgreSQL tsvector when available, falls back to LIKE on SQLite.
    """
    from ai_mailbox.db.connection import PostgresDB

    if isinstance(db, PostgresDB):
        return _search_postgres(db, user_id, query, project=project,
                                from_user=from_user, since=since,
                                until=until, limit=limit)
    return _search_sqlite(db, user_id, query, project=project,
                          from_user=from_user, since=since,
                          until=until, limit=limit)


def _search_postgres(
    db: DBConnection,
    user_id: str,
    query: str,
    *,
    project: str | None,
    from_user: str | None,
    since: str | None,
    until: str | None,
    limit: int,
) -> list[dict]:
    conditions = [
        "cp.user_id = ?",
        "m.search_vector @@ plainto_tsquery('english', ?)",
    ]
    params: list = [user_id, query]

    if project is not None:
        conditions.append("c.project = ?")
        params.append(project)
    if from_user is not None:
        conditions.append("m.from_user = ?")
        params.append(from_user)
    if since is not None:
        conditions.append("m.created_at >= ?")
        params.append(since)
    if until is not None:
        conditions.append("m.created_at <= ?")
        params.append(until)

    params.append(limit)
    where = " AND ".join(conditions)

    return db.fetchall(
        f"""SELECT m.id, m.conversation_id, m.from_user, m.sequence_number,
                   m.subject, m.body, m.content_type, m.idempotency_key,
                   m.reply_to, m.ack_state, m.created_at,
                   c.project, c.type,
                   ts_rank(m.search_vector, plainto_tsquery('english', ?)) AS rank
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            JOIN conversation_participants cp ON c.id = cp.conversation_id
            WHERE {where}
            ORDER BY rank DESC, m.created_at DESC
            LIMIT ?""",
        tuple([query] + params),
    )


def _search_sqlite(
    db: DBConnection,
    user_id: str,
    query: str,
    *,
    project: str | None,
    from_user: str | None,
    since: str | None,
    until: str | None,
    limit: int,
) -> list[dict]:
    # Escape LIKE special chars, then wrap with wildcards
    escaped = query.replace("%", "\\%").replace("_", "\\_")
    like_pattern = f"%{escaped}%"

    conditions = [
        "cp.user_id = ?",
        "(m.body LIKE ? ESCAPE '\\' OR m.subject LIKE ? ESCAPE '\\')",
    ]
    params: list = [user_id, like_pattern, like_pattern]

    if project is not None:
        conditions.append("c.project = ?")
        params.append(project)
    if from_user is not None:
        conditions.append("m.from_user = ?")
        params.append(from_user)
    if since is not None:
        conditions.append("m.created_at >= ?")
        params.append(since)
    if until is not None:
        conditions.append("m.created_at <= ?")
        params.append(until)

    params.append(limit)
    where = " AND ".join(conditions)

    return db.fetchall(
        f"""SELECT m.id, m.conversation_id, m.from_user, m.sequence_number,
                   m.subject, m.body, m.content_type, m.idempotency_key,
                   m.reply_to, m.ack_state, m.created_at,
                   c.project, c.type
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            JOIN conversation_participants cp ON c.id = cp.conversation_id
            WHERE {where}
            ORDER BY m.created_at DESC
            LIMIT ?""",
        tuple(params),
    )


# ---------------------------------------------------------------------------
# User queries
# ---------------------------------------------------------------------------

def get_user_projects(db: DBConnection, user_id: str) -> list[str]:
    """Return distinct project names for user's conversations."""
    rows = db.fetchall(
        """SELECT DISTINCT c.project FROM conversations c
           JOIN conversation_participants cp ON c.id = cp.conversation_id
           WHERE cp.user_id = ? AND c.project IS NOT NULL
           ORDER BY c.project""",
        (user_id,),
    )
    return [r["project"] for r in rows]


def get_user_conversation_partners(db: DBConnection, user_id: str) -> list[str]:
    """Return distinct user_ids the user shares conversations with."""
    rows = db.fetchall(
        """SELECT DISTINCT cp2.user_id FROM conversation_participants cp1
           JOIN conversation_participants cp2 ON cp1.conversation_id = cp2.conversation_id
           WHERE cp1.user_id = ? AND cp2.user_id != ?
           ORDER BY cp2.user_id""",
        (user_id, user_id),
    )
    return [r["user_id"] for r in rows]


def get_user(db: DBConnection, user_id: str) -> dict | None:
    """Fetch user by ID."""
    return db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))


def update_last_seen(db: DBConnection, user_id: str) -> None:
    """Update user's last_seen timestamp. Called on every MCP tool invocation."""
    db.execute(
        "UPDATE users SET last_seen = ? WHERE id = ?",
        (_now(), user_id),
    )


def get_all_users(db: DBConnection) -> list[dict]:
    """Fetch all users, excluding the reserved 'system' user."""
    return db.fetchall("SELECT * FROM users WHERE user_type != 'system' ORDER BY id", ())


# ---------------------------------------------------------------------------
# Dead letter handling
# ---------------------------------------------------------------------------

def is_user_offline(db: DBConnection, user_id: str) -> bool:
    """Check if a user is offline (last_seen older than threshold or NULL)."""
    user = get_user(db, user_id)
    if not user or not user.get("last_seen"):
        return True
    threshold = datetime.now(timezone.utc) - timedelta(hours=DEAD_LETTER_THRESHOLD_HOURS)
    # Parse last_seen — handle both ISO formats
    last_seen_str = user["last_seen"]
    try:
        last_seen = datetime.fromisoformat(last_seen_str)
    except (ValueError, TypeError):
        return True
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return last_seen < threshold


def process_dead_letters(db: DBConnection, user_id: str) -> int:
    """Transition queued messages to delivered for conversations the user participates in.

    Called when a previously-offline user becomes active again.
    Returns the number of messages transitioned.
    """
    rows = db.fetchall(
        """SELECT m.id FROM messages m
           JOIN conversation_participants cp ON m.conversation_id = cp.conversation_id
           WHERE cp.user_id = ? AND m.from_user != ? AND m.delivery_status = 'queued'""",
        (user_id, user_id),
    )
    if not rows:
        return 0
    ids = [r["id"] for r in rows]
    placeholders = ",".join("?" for _ in ids)
    db.execute(
        f"UPDATE messages SET delivery_status = 'delivered' WHERE id IN ({placeholders})",
        tuple(ids),
    )
    db.commit()
    return len(ids)


def get_dead_letters(db: DBConnection, user_id: str) -> list[dict]:
    """Return queued (undelivered) messages in conversations the user participates in."""
    return db.fetchall(
        """SELECT m.* FROM messages m
           JOIN conversation_participants cp ON m.conversation_id = cp.conversation_id
           WHERE cp.user_id = ? AND m.from_user != ? AND m.delivery_status = 'queued'
           ORDER BY m.created_at ASC""",
        (user_id, user_id),
    )


def update_last_seen_and_process_dead_letters(db: DBConnection, user_id: str) -> int:
    """Update last_seen and process any dead letters. Returns count of redelivered messages."""
    update_last_seen(db, user_id)
    return process_dead_letters(db, user_id)
