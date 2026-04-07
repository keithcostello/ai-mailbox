"""Schema management — ensures database tables exist on startup.

Supports both PostgreSQL (production) and SQLite (testing).
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_MIGRATION_DIR = Path(__file__).parent / "migrations"


_PG_ONLY_MIGRATIONS = {"004_search.sql", "005_pg_only_fk_fixes.sql", "007_nullable_to_user.sql", "010b_pg_only_profile_index.sql"}


def _split_pg_statements(sql: str) -> list[str]:
    """Split SQL respecting $$ dollar-quoted blocks (used in PL/pgSQL functions)."""
    statements = []
    current = []
    in_dollar_quote = False
    for line in sql.split("\n"):
        # Track $$ blocks — toggle on each occurrence
        count = line.count("$$")
        if count % 2 == 1:
            in_dollar_quote = not in_dollar_quote
        current.append(line)
        # Only split on ; when not inside a $$ block
        if not in_dollar_quote and line.rstrip().endswith(";"):
            statements.append("\n".join(current))
            current = []
    # Leftover (shouldn't happen with well-formed SQL)
    if current:
        remaining = "\n".join(current).strip()
        if remaining:
            statements.append(remaining)
    return statements


def get_migration_sql(*, exclude_pg_only: bool = False) -> str:
    """Read and concatenate all migration SQL files in order.

    When exclude_pg_only is True, skip migrations that rely on
    PostgreSQL-only features (tsvector, plpgsql, GIN indexes).
    """
    parts = []
    for f in sorted(_MIGRATION_DIR.glob("*.sql")):
        if exclude_pg_only and f.name in _PG_ONLY_MIGRATIONS:
            continue
        parts.append(f.read_text())
    return "\n\n".join(parts)


def _sqlite_make_to_user_nullable(conn: sqlite3.Connection) -> None:
    """Rebuild messages table so to_user allows NULL (SQLite has no ALTER COLUMN).

    Only runs if to_user exists and is NOT NULL. Idempotent.
    """
    cols = conn.execute("PRAGMA table_info(messages)").fetchall()
    to_user = [c for c in cols if c[1] == "to_user"]
    if not to_user or to_user[0][3] == 0:  # column absent or already nullable
        return

    # Get current column definitions (name, type, notnull, default)
    col_defs = []
    for c in cols:
        name, ctype, notnull, dflt, _pk = c[1], c[2], c[3], c[4], c[5]
        if name == "to_user":
            notnull = 0  # make nullable
        parts = [name, ctype or "TEXT"]
        if _pk:
            parts.append("PRIMARY KEY")
        if notnull and not _pk:
            parts.append("NOT NULL")
        if dflt is not None:
            parts.append(f"DEFAULT {dflt}")
        col_defs.append(" ".join(parts))

    col_names = ", ".join(c[1] for c in cols)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(f"CREATE TABLE messages_new ({', '.join(col_defs)})")
    conn.execute(f"INSERT INTO messages_new ({col_names}) SELECT {col_names} FROM messages")
    conn.execute("DROP TABLE messages")
    conn.execute("ALTER TABLE messages_new RENAME TO messages")
    # Recreate indexes
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_msg_seq
        ON messages(conversation_id, sequence_number)""")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_msg_idempotency
        ON messages(conversation_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_reply ON messages(reply_to) WHERE reply_to IS NOT NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_created ON messages(created_at)")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    logger.info("SQLite: to_user column made nullable (BUG-001)")


def ensure_schema_sqlite(conn: sqlite3.Connection) -> None:
    """Run migrations against a SQLite connection (for testing)."""
    sql = get_migration_sql(exclude_pg_only=True)
    # SQLite-compatible: strip PG-specific syntax
    sql = sql.replace("gen_random_uuid()", "'placeholder'")
    sql = sql.replace("NOW()", "CURRENT_TIMESTAMP")
    sql = sql.replace("UUID", "TEXT")
    sql = sql.replace("VARCHAR(64)", "TEXT")
    sql = sql.replace("VARCHAR(128)", "TEXT")
    sql = sql.replace("VARCHAR(256)", "TEXT")
    sql = sql.replace("BOOLEAN", "INTEGER")

    # Strip PG-specific ALTER TABLE IF NOT EXISTS syntax
    # Convert to plain ALTER TABLE (SQLite will error on duplicate, which we catch)
    sql = sql.replace("ADD COLUMN IF NOT EXISTS", "ADD COLUMN")

    # Execute statements one at a time, ignoring duplicate column errors
    for statement in sql.split(";"):
        statement = statement.strip()
        if not statement:
            continue
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                continue
            raise
        except sqlite3.IntegrityError as e:
            # Idempotent INSERT ... WHERE NOT EXISTS may still hit
            # unique constraints on re-run; safe to skip.
            if "unique" in str(e).lower():
                continue
            raise
    conn.commit()

    # BUG-001: SQLite cannot ALTER COLUMN, so rebuild messages table to make
    # to_user nullable (matching Postgres migration 007).
    _sqlite_make_to_user_nullable(conn)

    logger.info("SQLite schema migrations complete")


def ensure_schema_postgres(database_url: str) -> None:
    """Run migrations against PostgreSQL (production).

    Executes each statement individually with autocommit.
    Retries connection up to 5 times for Railway cold starts.
    """
    import psycopg
    import time as _time

    sql = get_migration_sql()

    # Retry connection for Railway cold starts
    for attempt in range(5):
        try:
            conn = psycopg.connect(database_url, autocommit=True)
            break
        except Exception as e:
            logger.warning(f"DB connection attempt {attempt + 1}/5 failed: {e}")
            if attempt == 4:
                raise
            _time.sleep(2)

    logger.info("Running PostgreSQL schema migrations")
    for statement in _split_pg_statements(sql):
        statement = statement.strip()
        if not statement:
            continue
        try:
            conn.execute(statement)
        except Exception as e:
            err_msg = str(e).lower()
            if "already exists" in err_msg or "duplicate" in err_msg:
                logger.debug(f"Skipping (expected): {e}")
                continue
            logger.error(f"Migration error: {e}")
            raise
    conn.close()
    logger.info("PostgreSQL schema migrations complete")

    # Run Python data migration for 003 (conversation model)
    from ai_mailbox.db.connection import PostgresDB
    from ai_mailbox.db.migrations.migrate_003 import migrate_003_data
    pg_db = PostgresDB(database_url)
    try:
        stats = migrate_003_data(pg_db)
        if stats["conversations_created"] > 0:
            logger.info(f"Migration 003 data: {stats}")
    except Exception as e:
        logger.warning(f"Migration 003 data step skipped: {e}")
