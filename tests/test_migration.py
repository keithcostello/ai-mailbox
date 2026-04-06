"""Tests for migration 003: conversation model schema."""
import sqlite3

import pytest


def _apply_old_schema(conn: sqlite3.Connection) -> None:
    """Apply Sprint 0 schema (pre-conversation model)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            api_key TEXT NOT NULL UNIQUE,
            password_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            from_user TEXT NOT NULL REFERENCES users(id),
            to_user TEXT NOT NULL REFERENCES users(id),
            project TEXT NOT NULL DEFAULT 'general',
            subject TEXT DEFAULT NULL,
            body TEXT NOT NULL,
            reply_to TEXT REFERENCES messages(id),
            read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_msg_inbox
            ON messages(to_user, project, read, created_at);
        CREATE INDEX IF NOT EXISTS idx_msg_thread ON messages(reply_to);
    """)


def _apply_new_schema_tables(conn: sqlite3.Connection) -> None:
    """Apply Sprint 1 new tables (conversations + participants)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL DEFAULT 'direct',
            project TEXT,
            name TEXT,
            created_by TEXT NOT NULL REFERENCES users(id),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS conversation_participants (
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id),
            joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_read_sequence INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (conversation_id, user_id)
        );
    """)


def _get_tables(conn: sqlite3.Connection) -> set[str]:
    """Return set of table names in database."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    return {row[0] for row in cursor.fetchall()}


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return set of column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


class TestNewSchemaOnEmptyDB:
    """Migration creates correct tables on a fresh database."""

    def test_conversations_table_exists(self, db):
        tables = _get_tables(db._conn)
        assert "conversations" in tables

    def test_conversation_participants_table_exists(self, db):
        tables = _get_tables(db._conn)
        assert "conversation_participants" in tables

    def test_messages_table_has_conversation_id(self, db):
        cols = _get_columns(db._conn, "messages")
        assert "conversation_id" in cols

    def test_messages_table_has_sequence_number(self, db):
        cols = _get_columns(db._conn, "messages")
        assert "sequence_number" in cols

    def test_messages_table_has_content_type(self, db):
        cols = _get_columns(db._conn, "messages")
        assert "content_type" in cols

    def test_messages_table_has_idempotency_key(self, db):
        cols = _get_columns(db._conn, "messages")
        assert "idempotency_key" in cols

    def test_messages_table_no_to_user(self, db):
        cols = _get_columns(db._conn, "messages")
        assert "to_user" not in cols

    def test_messages_table_no_read_column(self, db):
        cols = _get_columns(db._conn, "messages")
        assert "read" not in cols

    def test_conversations_columns(self, db):
        cols = _get_columns(db._conn, "conversations")
        expected = {"id", "type", "project", "name", "created_by", "created_at", "updated_at"}
        assert cols == expected

    def test_conversation_participants_columns(self, db):
        cols = _get_columns(db._conn, "conversation_participants")
        expected = {"conversation_id", "user_id", "joined_at", "last_read_sequence", "archived_at"}
        assert cols == expected

    def test_sequence_number_unique_per_conversation(self, db):
        """UNIQUE(conversation_id, sequence_number) enforced."""
        import uuid
        conv_id = str(uuid.uuid4())
        db._conn.execute(
            "INSERT INTO conversations (id, type, project, created_by) VALUES (?, 'direct', 'general', 'keith')",
            (conv_id,),
        )
        db._conn.execute(
            "INSERT INTO conversation_participants (conversation_id, user_id) VALUES (?, ?)",
            (conv_id, "keith"),
        )
        db._conn.execute(
            "INSERT INTO conversation_participants (conversation_id, user_id) VALUES (?, ?)",
            (conv_id, "amy"),
        )
        msg1_id = str(uuid.uuid4())
        db._conn.execute(
            "INSERT INTO messages (id, conversation_id, from_user, sequence_number, body) VALUES (?, ?, 'keith', 1, 'first')",
            (msg1_id, conv_id),
        )
        # Duplicate sequence_number in same conversation should fail
        msg2_id = str(uuid.uuid4())
        with pytest.raises(Exception):
            db._conn.execute(
                "INSERT INTO messages (id, conversation_id, from_user, sequence_number, body) VALUES (?, ?, 'amy', 1, 'duplicate')",
                (msg2_id, conv_id),
            )


class TestOldSchemaStructure:
    """Verify the old schema has the expected shape (pre-migration)."""

    def test_old_messages_has_to_user(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON")
        _apply_old_schema(conn)
        cols = _get_columns(conn, "messages")
        assert "to_user" in cols
        assert "read" in cols
        assert "conversation_id" not in cols
        conn.close()

    def test_old_schema_no_conversations_table(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON")
        _apply_old_schema(conn)
        tables = _get_tables(conn)
        assert "conversations" not in tables
        conn.close()


def _make_old_db_with_data() -> sqlite3.Connection:
    """Create an old-schema DB with seeded users and messages."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _apply_old_schema(conn)
    conn.execute("INSERT INTO users (id, display_name, api_key) VALUES ('keith', 'Keith', 'k1')")
    conn.execute("INSERT INTO users (id, display_name, api_key) VALUES ('amy', 'Amy', 'a1')")

    # 3 messages in general (one read), 1 in deployment
    conn.execute(
        "INSERT INTO messages (id, from_user, to_user, project, body, read, created_at) "
        "VALUES ('m1', 'keith', 'amy', 'general', 'msg1', 0, '2026-04-01T10:00:00')"
    )
    conn.execute(
        "INSERT INTO messages (id, from_user, to_user, project, body, reply_to, read, created_at) "
        "VALUES ('m2', 'amy', 'keith', 'general', 'msg2', 'm1', 1, '2026-04-01T10:01:00')"
    )
    conn.execute(
        "INSERT INTO messages (id, from_user, to_user, project, body, reply_to, read, created_at) "
        "VALUES ('m3', 'keith', 'amy', 'general', 'msg3', 'm2', 0, '2026-04-01T10:02:00')"
    )
    conn.execute(
        "INSERT INTO messages (id, from_user, to_user, project, body, read, created_at) "
        "VALUES ('m4', 'keith', 'amy', 'deployment', 'deploy msg', 0, '2026-04-01T11:00:00')"
    )
    conn.commit()

    # Add new tables + columns (simulating DDL part of migration 003)
    _apply_new_schema_tables(conn)
    conn.execute("ALTER TABLE messages ADD COLUMN conversation_id TEXT REFERENCES conversations(id)")
    conn.execute("ALTER TABLE messages ADD COLUMN sequence_number INTEGER")
    conn.execute("ALTER TABLE messages ADD COLUMN content_type TEXT DEFAULT 'text/plain'")
    conn.execute("ALTER TABLE messages ADD COLUMN idempotency_key TEXT")
    conn.commit()
    return conn


class TestDataMigration:
    """migrate_003_data migrates existing messages into conversations."""

    def test_creates_conversations_from_message_groups(self):
        from ai_mailbox.db.connection import SQLiteDB
        from ai_mailbox.db.migrations.migrate_003 import migrate_003_data
        conn = _make_old_db_with_data()
        db = SQLiteDB(conn)
        stats = migrate_003_data(db)
        # 2 conversations: (keith, amy, general) and (keith, amy, deployment)
        assert stats["conversations_created"] == 2
        conn.close()

    def test_all_messages_get_conversation_id(self):
        from ai_mailbox.db.connection import SQLiteDB
        from ai_mailbox.db.migrations.migrate_003 import migrate_003_data
        conn = _make_old_db_with_data()
        db = SQLiteDB(conn)
        migrate_003_data(db)
        unmigrated = conn.execute("SELECT COUNT(*) FROM messages WHERE conversation_id IS NULL").fetchone()[0]
        assert unmigrated == 0
        conn.close()

    def test_sequence_numbers_assigned(self):
        from ai_mailbox.db.connection import SQLiteDB
        from ai_mailbox.db.migrations.migrate_003 import migrate_003_data
        conn = _make_old_db_with_data()
        db = SQLiteDB(conn)
        migrate_003_data(db)
        # General conversation: 3 messages, sequences 1-3
        m1 = conn.execute("SELECT sequence_number FROM messages WHERE id = 'm1'").fetchone()
        m2 = conn.execute("SELECT sequence_number FROM messages WHERE id = 'm2'").fetchone()
        m3 = conn.execute("SELECT sequence_number FROM messages WHERE id = 'm3'").fetchone()
        assert m1[0] == 1
        assert m2[0] == 2
        assert m3[0] == 3
        # Deployment conversation: 1 message, sequence 1
        m4 = conn.execute("SELECT sequence_number FROM messages WHERE id = 'm4'").fetchone()
        assert m4[0] == 1
        conn.close()

    def test_participants_created(self):
        from ai_mailbox.db.connection import SQLiteDB
        from ai_mailbox.db.migrations.migrate_003 import migrate_003_data
        conn = _make_old_db_with_data()
        db = SQLiteDB(conn)
        stats = migrate_003_data(db)
        assert stats["participants_created"] == 4  # 2 per conversation * 2 conversations
        conn.close()

    def test_read_cursor_migrated(self):
        from ai_mailbox.db.connection import SQLiteDB
        from ai_mailbox.db.migrations.migrate_003 import migrate_003_data
        conn = _make_old_db_with_data()
        db = SQLiteDB(conn)
        migrate_003_data(db)
        # m2 was read by keith (to_user=keith, read=1), sequence=2
        # keith's last_read_sequence in general conv should be 2
        row = conn.execute(
            """SELECT cp.last_read_sequence FROM conversation_participants cp
               JOIN conversations c ON cp.conversation_id = c.id
               WHERE cp.user_id = 'keith' AND c.project = 'general'"""
        ).fetchone()
        assert row[0] == 2
        conn.close()

    def test_reply_to_preserved(self):
        from ai_mailbox.db.connection import SQLiteDB
        from ai_mailbox.db.migrations.migrate_003 import migrate_003_data
        conn = _make_old_db_with_data()
        db = SQLiteDB(conn)
        migrate_003_data(db)
        m2 = conn.execute("SELECT reply_to FROM messages WHERE id = 'm2'").fetchone()
        assert m2[0] == "m1"
        conn.close()

    def test_idempotent(self):
        from ai_mailbox.db.connection import SQLiteDB
        from ai_mailbox.db.migrations.migrate_003 import migrate_003_data
        conn = _make_old_db_with_data()
        db = SQLiteDB(conn)
        stats1 = migrate_003_data(db)
        stats2 = migrate_003_data(db)
        assert stats1["conversations_created"] == 2
        assert stats2["conversations_created"] == 0  # Already migrated
        conn.close()

    def test_empty_db_no_op(self):
        from ai_mailbox.db.connection import SQLiteDB
        from ai_mailbox.db.migrations.migrate_003 import migrate_003_data
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _apply_old_schema(conn)
        conn.execute("INSERT INTO users (id, display_name, api_key) VALUES ('keith', 'Keith', 'k1')")
        conn.commit()
        _apply_new_schema_tables(conn)
        conn.execute("ALTER TABLE messages ADD COLUMN conversation_id TEXT")
        conn.execute("ALTER TABLE messages ADD COLUMN sequence_number INTEGER")
        conn.commit()
        db = SQLiteDB(conn)
        stats = migrate_003_data(db)
        assert stats["conversations_created"] == 0
        assert stats["messages_migrated"] == 0
        conn.close()
