"""Authentication — validate API key and return user_id."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


class AuthError(Exception):
    """Raised when API key is invalid."""


def authenticate(db: DBConnection, api_key: str) -> str:
    """Validate api_key against users table. Returns user_id or raises AuthError."""
    row = db.fetchone("SELECT id FROM users WHERE api_key = ?", (api_key,))
    if row is None:
        raise AuthError("Invalid API key")
    return row["id"]
