"""Rate limiting for MCP tools and web routes."""

from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

storage = MemoryStorage()
limiter = MovingWindowRateLimiter(storage)

# Limit definitions (per spec section 3.2)
MCP_READ_LIMIT = parse("60/minute")     # list_messages, get_thread, whoami, list_users
MCP_WRITE_LIMIT = parse("30/minute")    # send_message, reply_to_message, mark_read
MCP_GROUP_LIMIT = parse("10/minute")    # create_group, add_participant
WEB_LOGIN_LIMIT = parse("5/minute")     # POST /web/login, POST /login
WEB_PAGE_LIMIT = parse("30/minute")     # GET /web/*


def check_rate_limit(limit, *identifiers) -> bool:
    """Returns True if within limit, False if exceeded."""
    return limiter.hit(limit, *identifiers)


def reset_storage():
    """Reset all rate limit state. Used in tests."""
    global storage, limiter
    storage = MemoryStorage()
    limiter = MovingWindowRateLimiter(storage)
