"""BUG-001: to_user NOT NULL constraint blocks all message sends.

The test conftest.py uses a clean-room schema without the legacy to_user column.
Production runs migrations sequentially: 001_initial.sql creates to_user NOT NULL,
003_conversation_model.sql adds conversation columns but never drops the constraint.
This test exercises the real migration path to prove the bug and verify the fix.
"""

import sqlite3

import pytest

from ai_mailbox.db.connection import SQLiteDB
from ai_mailbox.db.queries import find_or_create_direct_conversation, insert_message
from ai_mailbox.db.schema import ensure_schema_sqlite


@pytest.fixture
def migrated_db():
    """Build DB via the real migration path (ensure_schema_sqlite), not the test schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema_sqlite(conn)

    # Seed users
    conn.execute(
        "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
        ("keith", "Keith", "test-key-1"),
    )
    conn.execute(
        "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
        ("amy", "Amy", "test-key-2"),
    )
    conn.commit()
    yield SQLiteDB(conn)
    conn.close()


class TestToUserConstraint:
    """Prove that the real migration path allows insert_message to succeed."""

    def test_insert_message_succeeds_on_migrated_schema(self, migrated_db):
        """insert_message must work on a DB built via the real migration path.

        Before the fix, this fails with:
            NOT NULL constraint failed: messages.to_user
        """
        conv_id = find_or_create_direct_conversation(
            migrated_db, "keith", "amy", "general",
        )
        result = insert_message(migrated_db, conv_id, "keith", "hello from migrated schema")
        assert "id" in result
        assert result["sequence_number"] == 1

    def test_reply_succeeds_on_migrated_schema(self, migrated_db):
        """Reply path also exercises insert_message — must not fail on to_user."""
        conv_id = find_or_create_direct_conversation(
            migrated_db, "keith", "amy", "general",
        )
        msg = insert_message(migrated_db, conv_id, "keith", "original")
        reply = insert_message(
            migrated_db, conv_id, "amy", "reply",
            reply_to=msg["id"],
        )
        assert "id" in reply
        assert reply["sequence_number"] == 2

    def test_to_user_column_is_nullable_after_migration(self, migrated_db):
        """The to_user column (if present) must allow NULL values."""
        cols = migrated_db._conn.execute("PRAGMA table_info(messages)").fetchall()
        to_user_col = [c for c in cols if c[1] == "to_user"]
        if to_user_col:
            # notnull flag is column index 3; 0 means nullable
            assert to_user_col[0][3] == 0, "to_user must be nullable after migration"
