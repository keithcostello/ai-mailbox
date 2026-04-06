"""Web UI routes for AI Mailbox -- Jinja2 + HTMX + Tailwind.

Sprint 2: Real inbox data, pagination, login rate limiting.
Authentication via JWT stored in httpOnly session cookie.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import jwt
from jinja2 import Environment, FileSystemLoader
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from ai_mailbox.rate_limit import check_rate_limit, WEB_LOGIN_LIMIT, WEB_PAGE_LIMIT

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection
    from ai_mailbox.oauth import MailboxOAuthProvider

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)

INBOX_PAGE_SIZE = 20


def _render(template_name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    """Render a Jinja2 template to HTMLResponse."""
    tmpl = _jinja_env.get_template(template_name)
    return HTMLResponse(tmpl.render(**ctx), status_code=status_code)


def _get_session_user(request: Request, jwt_secret: str) -> str | None:
    """Extract user_id from session cookie JWT. Returns None if invalid/missing."""
    token = request.cookies.get("session")
    if not token:
        return None
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        return payload.get("sub")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def _get_user_display_name(db: DBConnection, user_id: str) -> str:
    """Get display name for a user."""
    row = db.fetchone("SELECT display_name FROM users WHERE id = ?", (user_id,))
    return row["display_name"] if row else user_id


def _client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def _relative_time(timestamp_str: str | None) -> str:
    """Convert ISO timestamp to relative time string."""
    if not timestamp_str:
        return ""
    try:
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - ts
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            m = seconds // 60
            return f"{m}m ago"
        if seconds < 86400:
            h = seconds // 3600
            return f"{h}h ago"
        d = seconds // 86400
        if d == 1:
            return "yesterday"
        if d < 30:
            return f"{d}d ago"
        return ts.strftime("%b %d")
    except (ValueError, TypeError):
        return str(timestamp_str)[:10] if timestamp_str else ""


# Register the filter so templates can use it
_jinja_env.filters["relative_time"] = _relative_time


def create_web_routes(db: DBConnection, provider: MailboxOAuthProvider, jwt_secret: str) -> list[Route]:
    """Create web UI routes. Returns list of Starlette Route objects."""

    async def web_login_get(request: Request):
        # If already logged in, redirect to inbox
        user_id = _get_session_user(request, jwt_secret)
        if user_id:
            return RedirectResponse(url="/web/inbox", status_code=302)
        return _render("login.html", error=None, user_id=None)

    async def web_login_post(request: Request):
        # Rate limit by IP
        ip = _client_ip(request)
        if not check_rate_limit(WEB_LOGIN_LIMIT, "login", ip):
            return _render(
                "login.html",
                error="Too many login attempts. Try again in 1 minute.",
                user_id=None,
                status_code=429,
            )

        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")

        user_id = provider.authenticate_user(username, password)
        if user_id is None:
            return _render("login.html", error="Invalid username or password", user_id=None)

        # Create JWT for session cookie
        import time
        token = jwt.encode(
            {"sub": user_id, "iat": int(time.time()), "exp": int(time.time()) + 86400},
            jwt_secret,
            algorithm="HS256",
        )

        response = RedirectResponse(url="/web/inbox", status_code=302)
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            samesite="lax",
            path="/web",
            max_age=86400,
        )
        return response

    async def web_logout(request: Request):
        response = RedirectResponse(url="/web/login", status_code=302)
        response.delete_cookie(key="session", path="/web")
        return response

    async def web_inbox(request: Request):
        user_id = _get_session_user(request, jwt_secret)
        if not user_id:
            return RedirectResponse(url="/web/login", status_code=302)

        # Rate limit
        if not check_rate_limit(WEB_PAGE_LIMIT, "web", user_id):
            return _render("login.html", error="Rate limit exceeded. Try again later.", user_id=None, status_code=429)

        from ai_mailbox.db.queries import get_inbox_paginated
        display_name = _get_user_display_name(db, user_id)

        # Pagination
        page = int(request.query_params.get("page", "1"))
        if page < 1:
            page = 1
        offset = (page - 1) * INBOX_PAGE_SIZE

        conversations, has_more = get_inbox_paginated(
            db, user_id, limit=INBOX_PAGE_SIZE, offset=offset,
        )

        return _render(
            "inbox.html",
            user_id=user_id,
            display_name=display_name,
            conversations=conversations,
            page=page,
            has_more=has_more,
            has_previous=page > 1,
        )

    async def web_health(request: Request):
        row = db.fetchone("SELECT COUNT(*) as cnt FROM users")
        user_count = row["cnt"] if row else 0
        health = {
            "status": "healthy",
            "version": "0.4.0",
            "user_count": user_count,
            "auth": "oauth2.1",
        }
        return _render("health.html", health=health, user_id=None)

    return [
        Route("/web/login", web_login_get, methods=["GET"]),
        Route("/web/login", web_login_post, methods=["POST"]),
        Route("/web/logout", web_logout, methods=["GET"]),
        Route("/web/inbox", web_inbox, methods=["GET"]),
        Route("/web/health", web_health, methods=["GET"]),
    ]
