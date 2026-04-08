"""Migration 010-011: profile_metadata column and approval_status column."""

from __future__ import annotations

import json
import sqlite3

import pytest

from ai_mailbox.db.connection import SQLiteDB
from ai_mailbox.db.schema import ensure_schema_sqlite


@pytest.fixture
def fresh_db():
    """Fresh in-memory SQLite with migrations applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema_sqlite(conn)
    return conn


class TestMigration010ProfileMetadata:
    """profile_metadata column on users table."""

    def test_column_exists(self, fresh_db):
        cols = [c[1] for c in fresh_db.execute("PRAGMA table_info(users)").fetchall()]
        assert "profile_metadata" in cols

    def test_default_is_empty_json(self, fresh_db):
        fresh_db.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("test", "Test", "key1"),
        )
        row = fresh_db.execute("SELECT profile_metadata FROM users WHERE id = 'test'").fetchone()
        assert row["profile_metadata"] == "{}"

    def test_stores_json(self, fresh_db):
        meta = json.dumps({"team": "engineering", "expertise_tags": ["python", "mcp"]})
        fresh_db.execute(
            "INSERT INTO users (id, display_name, api_key, profile_metadata) VALUES (?, ?, ?, ?)",
            ("test", "Test", "key1", meta),
        )
        row = fresh_db.execute("SELECT profile_metadata FROM users WHERE id = 'test'").fetchone()
        parsed = json.loads(row["profile_metadata"])
        assert parsed["team"] == "engineering"
        assert "python" in parsed["expertise_tags"]

    def test_idempotent_rerun(self, fresh_db):
        """Running migrations twice does not error."""
        ensure_schema_sqlite(fresh_db)
        cols = [c[1] for c in fresh_db.execute("PRAGMA table_info(users)").fetchall()]
        assert "profile_metadata" in cols


class TestMigration011ApprovalStatus:
    """approval_status column on messages table."""

    def test_column_exists(self, fresh_db):
        cols = [c[1] for c in fresh_db.execute("PRAGMA table_info(messages)").fetchall()]
        assert "approval_status" in cols

    def test_default_is_null(self, fresh_db):
        fresh_db.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("alice", "Alice", "k1"),
        )
        fresh_db.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("bob", "Bob", "k2"),
        )
        # Need a conversation for the message
        fresh_db.execute(
            "INSERT INTO conversations (id, type, project, created_by, created_at, updated_at) "
            "VALUES ('c1', 'direct', 'general', 'alice', '2026-01-01', '2026-01-01')"
        )
        fresh_db.execute(
            "INSERT INTO conversation_participants (conversation_id, user_id, joined_at) "
            "VALUES ('c1', 'alice', '2026-01-01')"
        )
        fresh_db.execute(
            "INSERT INTO messages (id, conversation_id, from_user, sequence_number, body, created_at) "
            "VALUES ('m1', 'c1', 'alice', 1, 'test', '2026-01-01')"
        )
        row = fresh_db.execute("SELECT approval_status FROM messages WHERE id = 'm1'").fetchone()
        assert row["approval_status"] is None

    def test_accepts_valid_values(self, fresh_db):
        fresh_db.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("alice", "Alice", "k1"),
        )
        fresh_db.execute(
            "INSERT INTO conversations (id, type, project, created_by, created_at, updated_at) "
            "VALUES ('c1', 'direct', 'general', 'alice', '2026-01-01', '2026-01-01')"
        )
        fresh_db.execute(
            "INSERT INTO conversation_participants (conversation_id, user_id, joined_at) "
            "VALUES ('c1', 'alice', '2026-01-01')"
        )
        fresh_db.execute(
            "INSERT INTO messages (id, conversation_id, from_user, sequence_number, body, "
            "created_at, approval_status) "
            "VALUES ('m1', 'c1', 'alice', 1, 'test', '2026-01-01', 'pending_human_approval')"
        )
        row = fresh_db.execute("SELECT approval_status FROM messages WHERE id = 'm1'").fetchone()
        assert row["approval_status"] == "pending_human_approval"

    def test_idempotent_rerun(self, fresh_db):
        ensure_schema_sqlite(fresh_db)
        cols = [c[1] for c in fresh_db.execute("PRAGMA table_info(messages)").fetchall()]
        assert "approval_status" in cols
