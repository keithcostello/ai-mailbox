"""Schema management — ensures database tables exist on startup.

Supports both PostgreSQL (production) and SQLite (testing).
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_MIGRATION_DIR = Path(__file__).parent / "migrations"


_PG_ONLY_MIGRATIONS = {"004_search.sql"}


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
    conn.commit()
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
