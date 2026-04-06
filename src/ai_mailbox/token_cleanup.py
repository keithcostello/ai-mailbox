"""Cleanup expired OAuth authorization codes and access tokens."""

import logging
import time

logger = logging.getLogger(__name__)


def cleanup_expired_tokens(db) -> dict:
    """Delete expired OAuth codes and tokens. Returns deletion counts."""
    now = time.time()

    codes_cursor = db.execute("DELETE FROM oauth_codes WHERE expires_at < ?", (now,))
    codes_deleted = codes_cursor.rowcount if hasattr(codes_cursor, 'rowcount') else 0

    tokens_cursor = db.execute(
        "DELETE FROM oauth_tokens WHERE expires_at IS NOT NULL AND expires_at < ?",
        (int(now),),
    )
    tokens_deleted = tokens_cursor.rowcount if hasattr(tokens_cursor, 'rowcount') else 0

    if codes_deleted or tokens_deleted:
        logger.info(
            f"Token cleanup: {codes_deleted} expired codes, "
            f"{tokens_deleted} expired tokens removed"
        )

    return {"codes_deleted": codes_deleted, "tokens_deleted": tokens_deleted}
