"""Web UI routes for AI Mailbox -- Jinja2 + HTMX + Tailwind.

Sprint 1 scaffold: login, inbox (read-only), health, logout.
Authentication via JWT stored in httpOnly session cookie.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import jwt
from jinja2 import Environment, FileSystemLoader
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection
    from ai_mailbox.oauth import MailboxOAuthProvider

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)


def _render(template_name: str, **ctx) -> HTMLResponse:
    """Render a Jinja2 template to HTMLResponse."""
    tmpl = _jinja_env.get_template(template_name)
    return HTMLResponse(tmpl.render(**ctx))


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


def create_web_routes(db: DBConnection, provider: MailboxOAuthProvider, jwt_secret: str) -> list[Route]:
    """Create web UI routes. Returns list of Starlette Route objects."""

    async def web_login_get(request: Request):
        # If already logged in, redirect to inbox
        user_id = _get_session_user(request, jwt_secret)
        if user_id:
            return RedirectResponse(url="/web/inbox", status_code=302)
        return _render("login.html", error=None, user_id=None)

    async def web_login_post(request: Request):
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

        from ai_mailbox.db.queries import get_inbox
        display_name = _get_user_display_name(db, user_id)
        conversations = get_inbox(db, user_id)

        return _render(
            "inbox.html",
            user_id=user_id,
            display_name=display_name,
            conversations=conversations,
        )

    async def web_health(request: Request):
        row = db.fetchone("SELECT COUNT(*) as cnt FROM users")
        user_count = row["cnt"] if row else 0
        health = {
            "status": "healthy",
            "version": "0.3.0",
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
