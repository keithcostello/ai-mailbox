"""Data migration for 003: conversation model.

Migrates existing flat messages (with to_user, read, project columns)
into the three-table conversation model. Safe to re-run (idempotent).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection

logger = logging.getLogger(__name__)


def _has_column(db: DBConnection, table: str, column: str) -> bool:
    """Check if a column exists in a table (SQLite-compatible)."""
    try:
        db.fetchone(f"SELECT {column} FROM {table} LIMIT 0")
        return True
    except Exception:
        return False


def migrate_003_data(db: DBConnection) -> dict:
    """Migrate existing messages into conversation model.

    Returns stats: {conversations_created, messages_migrated, participants_created}.
    """
    stats = {"conversations_created": 0, "messages_migrated": 0, "participants_created": 0}

    # Check if migration is needed: messages table must still have to_user column
    if not _has_column(db, "messages", "to_user"):
        logger.info("Migration 003: to_user column not found, migration already complete or fresh schema")
        return stats

    # Check if any messages lack conversation_id (need migration)
    if not _has_column(db, "messages", "conversation_id"):
        logger.info("Migration 003: conversation_id column not found, DDL not applied yet")
        return stats

    unmigrated = db.fetchone(
        "SELECT COUNT(*) as cnt FROM messages WHERE conversation_id IS NULL"
    )
    if not unmigrated or unmigrated["cnt"] == 0:
        logger.info("Migration 003: no unmigrated messages found")
        return stats

    logger.info(f"Migration 003: {unmigrated['cnt']} messages to migrate")

    # Step 1: Find unique (user_pair, project) groups
    groups = db.fetchall(
        """SELECT DISTINCT
               CASE WHEN from_user < to_user THEN from_user ELSE to_user END AS user_a,
               CASE WHEN from_user < to_user THEN to_user ELSE from_user END AS user_b,
               project
           FROM messages
           WHERE conversation_id IS NULL""",
        (),
    )

    # Step 2: For each group, create a conversation and link messages
    for group in groups:
        user_a = group["user_a"]
        user_b = group["user_b"]
        project = group["project"]

        # Check if conversation already exists
        existing = db.fetchone(
            """SELECT c.id FROM conversations c
               JOIN conversation_participants cp1 ON c.id = cp1.conversation_id AND cp1.user_id = ?
               JOIN conversation_participants cp2 ON c.id = cp2.conversation_id AND cp2.user_id = ?
               WHERE c.type = 'direct' AND c.project = ?""",
            (user_a, user_b, project),
        )

        if existing:
            conv_id = existing["id"]
        else:
            conv_id = str(uuid4())
            now = datetime.now(timezone.utc).isoformat()

            # Get earliest and latest message timestamps for this group
            time_range = db.fetchone(
                """SELECT MIN(created_at) as earliest, MAX(created_at) as latest
                   FROM messages
                   WHERE conversation_id IS NULL
                     AND CASE WHEN from_user < to_user THEN from_user ELSE to_user END = ?
                     AND CASE WHEN from_user < to_user THEN to_user ELSE from_user END = ?
                     AND project = ?""",
                (user_a, user_b, project),
            )

            db.execute(
                """INSERT INTO conversations (id, type, project, created_by, created_at, updated_at)
                   VALUES (?, 'direct', ?, ?, ?, ?)""",
                (conv_id, project, user_a,
                 time_range["earliest"] or now,
                 time_range["latest"] or now),
            )
            stats["conversations_created"] += 1

            # Add participants
            db.execute(
                "INSERT INTO conversation_participants (conversation_id, user_id, joined_at) VALUES (?, ?, ?)",
                (conv_id, user_a, time_range["earliest"] or now),
            )
            db.execute(
                "INSERT INTO conversation_participants (conversation_id, user_id, joined_at) VALUES (?, ?, ?)",
                (conv_id, user_b, time_range["earliest"] or now),
            )
            stats["participants_created"] += 2

        # Link messages to this conversation
        db.execute(
            """UPDATE messages SET conversation_id = ?
               WHERE conversation_id IS NULL
                 AND CASE WHEN from_user < to_user THEN from_user ELSE to_user END = ?
                 AND CASE WHEN from_user < to_user THEN to_user ELSE from_user END = ?
                 AND project = ?""",
            (conv_id, user_a, user_b, project),
        )

    # Step 3: Assign sequence numbers within each conversation by created_at order
    conversations_with_msgs = db.fetchall(
        "SELECT DISTINCT conversation_id FROM messages WHERE conversation_id IS NOT NULL AND sequence_number IS NULL",
        (),
    )
    for row in conversations_with_msgs:
        cid = row["conversation_id"]
        msgs = db.fetchall(
            "SELECT id FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (cid,),
        )
        for i, msg in enumerate(msgs, 1):
            db.execute(
                "UPDATE messages SET sequence_number = ? WHERE id = ?",
                (i, msg["id"]),
            )
            stats["messages_migrated"] += 1

    # Step 4: Set last_read_sequence for participants based on old read flags
    if _has_column(db, "messages", "read"):
        participants = db.fetchall(
            "SELECT conversation_id, user_id FROM conversation_participants",
            (),
        )
        for p in participants:
            # Find the max sequence_number of messages that were read by this user
            # In the old schema, "read" means the to_user has read it
            max_read = db.fetchone(
                """SELECT MAX(m.sequence_number) as max_seq
                   FROM messages m
                   WHERE m.conversation_id = ?
                     AND m.to_user = ?
                     AND m.read = 1""",
                (p["conversation_id"], p["user_id"]),
            )
            if max_read and max_read["max_seq"]:
                db.execute(
                    "UPDATE conversation_participants SET last_read_sequence = ? WHERE conversation_id = ? AND user_id = ?",
                    (max_read["max_seq"], p["conversation_id"], p["user_id"]),
                )

    db.commit()
    logger.info(f"Migration 003 complete: {stats}")
    return stats
