"""Test fixtures -- SQLite in-memory DB via real migration path."""

import sqlite3

import pytest

from ai_mailbox.db.connection import SQLiteDB
from ai_mailbox.db.schema import ensure_schema_sqlite

KEITH_API_KEY = "test-keith-key-abc123"
AMY_API_KEY = "test-amy-key-xyz789"
BOB_API_KEY = "test-bob-key-def456"
CHARLIE_API_KEY = "test-charlie-key-ghi789"


@pytest.fixture
def db():
    """In-memory SQLite database via real migration path, seeded with two test users."""
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


@pytest.fixture
def bob(db):
    """Create a third test user 'bob'."""
    db._conn.execute(
        "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
        ("bob", "Bob", BOB_API_KEY),
    )
    db._conn.commit()
    return "bob"


@pytest.fixture
def charlie(db):
    """Create a fourth test user 'charlie'."""
    db._conn.execute(
        "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
        ("charlie", "Charlie", CHARLIE_API_KEY),
    )
    db._conn.commit()
    return "charlie"
