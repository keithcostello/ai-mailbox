"""Schema parity guard -- ensures test fixtures match the real migration path.

Prevents BUG-001-class bugs where the test schema diverges from production.
"""

import sqlite3

from ai_mailbox.db.schema import ensure_schema_sqlite


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def _build_migration_db() -> sqlite3.Connection:
    """Build a standalone DB via ensure_schema_sqlite (not the conftest fixture)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema_sqlite(conn)
    return conn


class TestSchemaParity:
    """Verify conftest db fixture matches the real migration path."""

    def test_messages_columns_match(self, db):
        ref_conn = _build_migration_db()
        ref_cols = _get_columns(ref_conn, "messages")
        fixture_cols = _get_columns(db._conn, "messages")
        assert fixture_cols == ref_cols, f"Column mismatch: fixture={fixture_cols}, migration={ref_cols}"
        ref_conn.close()

    def test_conversations_columns_match(self, db):
        ref_conn = _build_migration_db()
        ref_cols = _get_columns(ref_conn, "conversations")
        fixture_cols = _get_columns(db._conn, "conversations")
        assert fixture_cols == ref_cols
        ref_conn.close()

    def test_participants_columns_match(self, db):
        ref_conn = _build_migration_db()
        ref_cols = _get_columns(ref_conn, "conversation_participants")
        fixture_cols = _get_columns(db._conn, "conversation_participants")
        assert fixture_cols == ref_cols
        ref_conn.close()

    def test_to_user_nullable_if_present(self, db):
        cols = db._conn.execute("PRAGMA table_info(messages)").fetchall()
        to_user = [c for c in cols if c[1] == "to_user"]
        if to_user:
            assert to_user[0][3] == 0, "to_user must be nullable (BUG-001)"
