"""Database connection abstraction — works with both SQLite and PostgreSQL.

Wraps both connection types behind a common interface so tool code
doesn't need to know which database is in use.
"""

import logging
import sqlite3
from typing import Protocol, Any

logger = logging.getLogger(__name__)


class DBConnection(Protocol):
    """Minimal database connection interface used by queries and tools."""

    def execute(self, sql: str, params: tuple = ()) -> Any: ...
    def fetchone(self, sql: str, params: tuple = ()) -> dict | None: ...
    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]: ...
    def commit(self) -> None: ...


class SQLiteDB:
    """SQLite wrapper implementing DBConnection."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def execute(self, sql: str, params: tuple = ()) -> Any:
        return self._conn.execute(sql, params)

    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def commit(self) -> None:
        self._conn.commit()


class PostgresDB:
    """PostgreSQL wrapper with auto-reconnect."""

    def __init__(self, database_url: str):
        self._database_url = database_url
        self._conn = None
        self._connect()

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row
        self._conn = psycopg.connect(
            self._database_url, row_factory=dict_row, autocommit=True
        )

    def _ensure_conn(self):
        """Reconnect if connection is closed."""
        if self._conn is None or self._conn.closed:
            logger.info("PostgreSQL connection lost, reconnecting...")
            self._connect()

    def execute(self, sql: str, params: tuple = ()) -> Any:
        sql = sql.replace("?", "%s")
        self._ensure_conn()
        try:
            return self._conn.execute(sql, params)
        except Exception:
            self._connect()
            return self._conn.execute(sql, params)

    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        sql = sql.replace("?", "%s")
        self._ensure_conn()
        try:
            cur = self._conn.execute(sql, params)
            return cur.fetchone()
        except Exception:
            self._connect()
            cur = self._conn.execute(sql, params)
            return cur.fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        sql = sql.replace("?", "%s")
        self._ensure_conn()
        try:
            cur = self._conn.execute(sql, params)
            return cur.fetchall()
        except Exception:
            self._connect()
            cur = self._conn.execute(sql, params)
            return cur.fetchall()

    def commit(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.commit()
