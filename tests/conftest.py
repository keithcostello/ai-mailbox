"""Test fixtures — SQLite in-memory DB with seeded users."""

import sqlite3

import pytest

from ai_mailbox.db.connection import SQLiteDB
from ai_mailbox.db.schema import ensure_schema_sqlite

KEITH_API_KEY = "test-keith-key-abc123"
AMY_API_KEY = "test-amy-key-xyz789"


@pytest.fixture
def db():
    """In-memory SQLite database with schema and two test users."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema_sqlite(conn)

    # Seed test users
    conn.execute(
        "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
        ("keith", "Keith", KEITH_API_KEY),
    )
    conn.execute(
        "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
        ("amy", "Amy", AMY_API_KEY),
    )
    conn.commit()

    yield SQLiteDB(conn)
    conn.close()
