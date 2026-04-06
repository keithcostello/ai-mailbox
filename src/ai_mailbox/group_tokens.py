"""Group send confirmation tokens.

Every group message requires a server-generated token obtained from
a confirmation payload. Tokens are single-use, bound to a specific
conversation + body hash, and expire after TOKEN_TTL_SECONDS.
"""

import hashlib
import time
import uuid

TOKEN_TTL_SECONDS = 300  # 5 minutes

# In-memory token store: {token_str: {conversation_id, body_hash, expires_at}}
_token_store: dict[str, dict] = {}


def _body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def generate_token(conversation_id: str, body: str) -> str:
    """Generate a single-use token bound to conversation_id + body."""
    token = str(uuid.uuid4())
    _token_store[token] = {
        "conversation_id": conversation_id,
        "body_hash": _body_hash(body),
        "expires_at": time.time() + TOKEN_TTL_SECONDS,
    }
    return token


def validate_token(
    token: str | None, conversation_id: str, body: str
) -> tuple[bool, str | None]:
    """Validate and consume a group send token.

    Returns (True, None) on success.
    Returns (False, error_code) on failure.
    """
    if not token or token not in _token_store:
        return False, "GROUP_TOKEN_INVALID"

    entry = _token_store[token]

    # Check expiry before consuming
    if time.time() > entry["expires_at"]:
        del _token_store[token]
        return False, "GROUP_TOKEN_EXPIRED"

    # Check binding
    if (
        entry["conversation_id"] != conversation_id
        or entry["body_hash"] != _body_hash(body)
    ):
        return False, "GROUP_TOKEN_INVALID"

    # Consume (single-use)
    del _token_store[token]
    return True, None


def clear_tokens():
    """Remove all tokens. Used in tests."""
    _token_store.clear()
