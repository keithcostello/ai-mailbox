"""Database connection abstraction — works with both SQLite and PostgreSQL.

Wraps both connection types behind a common interface so tool code
doesn't need to know which database is in use.
"""

import sqlite3
from typing import Protocol, Any


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
    """PostgreSQL wrapper implementing DBConnection. Uses psycopg."""

    def __init__(self, database_url: str):
        import psycopg
        from psycopg.rows import dict_row
        self._conn = psycopg.connect(database_url, row_factory=dict_row, autocommit=True)

    def execute(self, sql: str, params: tuple = ()) -> Any:
        # Convert ? placeholders to %s for psycopg
        sql = sql.replace("?", "%s")
        return self._conn.execute(sql, params)

    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        sql = sql.replace("?", "%s")
        cur = self._conn.execute(sql, params)
        return cur.fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        sql = sql.replace("?", "%s")
        cur = self._conn.execute(sql, params)
        return cur.fetchall()

    def commit(self) -> None:
        self._conn.commit()
