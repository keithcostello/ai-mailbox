"""Migration 013-014: broadcast_requests and broadcast_claims tables."""

from __future__ import annotations

import sqlite3

import pytest

from ai_mailbox.db.schema import ensure_schema_sqlite


@pytest.fixture
def fresh_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema_sqlite(conn)
    return conn


class TestMigration013BroadcastRequests:

    def test_table_exists(self, fresh_db):
        tables = [r[0] for r in fresh_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "broadcast_requests" in tables

    def test_columns(self, fresh_db):
        cols = [c[1] for c in fresh_db.execute("PRAGMA table_info(broadcast_requests)").fetchall()]
        for col in ("id", "from_user", "question", "source_context", "tags",
                     "project", "status", "conversation_id", "response_message_id",
                     "expires_at", "created_at", "updated_at"):
            assert col in cols, f"Missing column: {col}"

    def test_default_status_is_open(self, fresh_db):
        fresh_db.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES ('u1', 'U1', 'k1')"
        )
        fresh_db.execute(
            "INSERT INTO broadcast_requests (id, from_user, question, tags, created_at, updated_at) "
            "VALUES ('b1', 'u1', 'test?', '[]', '2026-01-01', '2026-01-01')"
        )
        row = fresh_db.execute("SELECT status FROM broadcast_requests WHERE id = 'b1'").fetchone()
        assert row["status"] == "open"

    def test_idempotent(self, fresh_db):
        ensure_schema_sqlite(fresh_db)
        tables = [r[0] for r in fresh_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "broadcast_requests" in tables


class TestMigration014BroadcastClaims:

    def test_table_exists(self, fresh_db):
        tables = [r[0] for r in fresh_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "broadcast_claims" in tables

    def test_columns(self, fresh_db):
        cols = [c[1] for c in fresh_db.execute("PRAGMA table_info(broadcast_claims)").fetchall()]
        for col in ("id", "broadcast_id", "claimant_id", "status",
                     "gate1_approved_at", "gate1_declined_at",
                     "gate2_approved_at", "gate2_declined_at",
                     "response_draft", "seen_at", "cooldown_until",
                     "created_at", "updated_at"):
            assert col in cols, f"Missing column: {col}"

    def test_unique_constraint(self, fresh_db):
        fresh_db.execute("INSERT INTO users (id, display_name, api_key) VALUES ('u1', 'U1', 'k1')")
        fresh_db.execute("INSERT INTO users (id, display_name, api_key) VALUES ('u2', 'U2', 'k2')")
        fresh_db.execute(
            "INSERT INTO broadcast_requests (id, from_user, question, tags, created_at, updated_at) "
            "VALUES ('b1', 'u1', 'test?', '[]', '2026-01-01', '2026-01-01')"
        )
        fresh_db.execute(
            "INSERT INTO broadcast_claims (id, broadcast_id, claimant_id, seen_at, created_at, updated_at) "
            "VALUES ('c1', 'b1', 'u2', '2026-01-01', '2026-01-01', '2026-01-01')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO broadcast_claims (id, broadcast_id, claimant_id, seen_at, created_at, updated_at) "
                "VALUES ('c2', 'b1', 'u2', '2026-01-01', '2026-01-01', '2026-01-01')"
            )

    def test_idempotent(self, fresh_db):
        ensure_schema_sqlite(fresh_db)
        tables = [r[0] for r in fresh_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "broadcast_claims" in tables
