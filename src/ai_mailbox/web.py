"""Web UI routes for AI Mailbox -- DaisyUI + Tailwind + HTMX.

Sprint 3: DaisyUI migration, error pages, AI badge, markdown rendering.
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

from markupsafe import Markup

from ai_mailbox.config import MAX_BODY_LENGTH
from ai_mailbox.markdown import render_markdown
from ai_mailbox.rate_limit import check_rate_limit, WEB_LOGIN_LIMIT, WEB_PAGE_LIMIT

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection
    from ai_mailbox.oauth import MailboxOAuthProvider

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)

INBOX_PAGE_SIZE = 20

# --- AI user badge heuristic ---
_AI_PATTERNS = {"claude", "gpt", "bot", "gemini", "copilot"}


def _is_ai_user(user_id: str) -> bool:
    """Heuristic: identify AI/bot users by name pattern."""
    lower = user_id.lower()
    return any(pat in lower for pat in _AI_PATTERNS) or lower.startswith("ai-")


# Register Jinja2 globals and filters
_jinja_env.globals["is_ai_user"] = _is_ai_user
_jinja_env.filters["markdown"] = lambda text: Markup(render_markdown(text)) if text else Markup("")


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


_ERROR_CONFIGS = {
    404: ("Not Found", "The page or conversation you requested does not exist."),
    403: ("Forbidden", "You do not have permission to access this resource."),
    429: ("Too Many Requests", "You've made too many requests. Wait a moment and try again."),
    500: ("Server Error", "Something went wrong. Try again or contact support."),
}


def _render_error(status_code: int, request=None, user_id=None, display_name=None, message=None) -> HTMLResponse:
    """Render a DaisyUI error page."""
    title, default_msg = _ERROR_CONFIGS.get(status_code, ("Error", "An error occurred."))
    tmpl = _jinja_env.get_template("error.html")
    html = tmpl.render(
        error_code=status_code,
        error_title=title,
        error_message=message or default_msg,
        user_id=user_id,
        display_name=display_name,
    )
    return HTMLResponse(html, status_code=status_code)


def _htmx_error(status_code: int, message: str | None = None) -> HTMLResponse:
    """Return inline error for HTMX requests."""
    title, default_msg = _ERROR_CONFIGS.get(status_code, ("Error", "An error occurred."))
    msg = message or default_msg
    return HTMLResponse(
        f'<div class="alert alert-error"><span>{msg}</span></div>',
        status_code=status_code,
    )


def create_web_routes(db: DBConnection, provider: MailboxOAuthProvider, jwt_secret: str) -> list[Route]:
    """Create web UI routes. Returns list of Starlette Route objects."""

    from ai_mailbox.db.queries import (
        advance_read_cursor,
        find_or_create_direct_conversation,
        get_all_users,
        get_conversation,
        get_conversation_messages,
        get_conversation_participants,
        get_inbox_paginated,
        get_max_sequence,
        get_user,
        get_user_conversation_partners,
        get_user_projects,
        insert_message,
    )

    # --- Auth helpers ---

    def _require_auth(request):
        """Returns user_id or None. Caller should redirect if None."""
        return _get_session_user(request, jwt_secret)

    def _is_htmx(request):
        """Check if request is from HTMX."""
        return request.headers.get("HX-Request") == "true"

    # --- Login / Logout ---

    async def web_login_get(request: Request):
        user_id = _require_auth(request)
        if user_id:
            return RedirectResponse(url="/web/inbox", status_code=302)
        return _render("login.html", error=None, user_id=None)

    async def web_login_post(request: Request):
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

        import time
        token = jwt.encode(
            {"sub": user_id, "iat": int(time.time()), "exp": int(time.time()) + 86400},
            jwt_secret,
            algorithm="HS256",
        )

        response = RedirectResponse(url="/web/inbox", status_code=302)
        response.set_cookie(
            key="session", value=token, httponly=True,
            samesite="lax", path="/web", max_age=86400,
        )
        return response

    async def web_logout(request: Request):
        response = RedirectResponse(url="/web/login", status_code=302)
        response.delete_cookie(key="session", path="/web")
        return response

    # --- Inbox (two-panel layout) ---

    async def web_inbox(request: Request):
        user_id = _require_auth(request)
        if not user_id:
            return RedirectResponse(url="/web/login", status_code=302)

        if not check_rate_limit(WEB_PAGE_LIMIT, "web", user_id):
            return _render_error(429, user_id=user_id)

        display_name = _get_user_display_name(db, user_id)
        projects = get_user_projects(db, user_id)
        partners = get_user_conversation_partners(db, user_id)

        project_filter = request.query_params.get("project", "")
        participant_filter = request.query_params.get("participant", "")

        return _render(
            "inbox.html",
            user_id=user_id,
            display_name=display_name,
            projects=projects,
            partners=partners,
            project_filter=project_filter,
            participant_filter=participant_filter,
            thread_content=None,
        )

    # --- Conversation list partial (sidebar) ---

    async def web_conversation_list(request: Request):
        user_id = _require_auth(request)
        if not user_id:
            return RedirectResponse(url="/web/login", status_code=302)

        if not check_rate_limit(WEB_PAGE_LIMIT, "web", user_id):
            return _htmx_error(429)

        project_filter = request.query_params.get("project", "")
        participant_filter = request.query_params.get("participant", "")
        page = int(request.query_params.get("page", "1"))
        if page < 1:
            page = 1
        offset = (page - 1) * INBOX_PAGE_SIZE

        conversations, has_more = get_inbox_paginated(
            db, user_id,
            project=project_filter or None,
            limit=INBOX_PAGE_SIZE, offset=offset,
        )

        # Filter by participant if specified
        if participant_filter:
            conversations = [
                c for c in conversations
                if participant_filter in c.get("participants", [])
            ]

        return _render(
            "partials/conversation_list.html",
            user_id=user_id,
            conversations=conversations,
            has_more=has_more,
            page=page,
            project_filter=project_filter,
            participant_filter=participant_filter,
        )

    # --- Thread view ---

    async def web_conversation(request: Request):
        user_id = _require_auth(request)
        if not user_id:
            return RedirectResponse(url="/web/login", status_code=302)

        display_name = _get_user_display_name(db, user_id)

        if not check_rate_limit(WEB_PAGE_LIMIT, "web", user_id):
            if _is_htmx(request):
                return _htmx_error(429)
            return _render_error(429, user_id=user_id, display_name=display_name)

        conv_id = request.path_params["conv_id"]
        try:
            conv = get_conversation(db, conv_id)
        except Exception:
            conv = None
        if not conv:
            if _is_htmx(request):
                return _htmx_error(404)
            return _render_error(404, user_id=user_id, display_name=display_name)

        participants = get_conversation_participants(db, conv_id)
        if user_id not in participants:
            if _is_htmx(request):
                return _htmx_error(403)
            return _render_error(403, user_id=user_id, display_name=display_name)

        messages, _ = get_conversation_messages(db, conv_id)

        # Auto-mark-read
        max_seq = get_max_sequence(db, conv_id)
        if max_seq > 0:
            advance_read_cursor(db, conv_id, user_id, max_seq)

        thread_html = _render(
            "partials/thread_view.html",
            user_id=user_id,
            conversation=conv,
            participants=participants,
            messages=[dict(m) for m in messages],
        ).body.decode("utf-8")

        # If HTMX request, return just the partial
        if _is_htmx(request):
            return HTMLResponse(thread_html)

        # Full-page: render inbox with thread pre-loaded
        display_name = _get_user_display_name(db, user_id)
        projects = get_user_projects(db, user_id)
        partners = get_user_conversation_partners(db, user_id)

        return _render(
            "inbox.html",
            user_id=user_id,
            display_name=display_name,
            projects=projects,
            partners=partners,
            project_filter="",
            participant_filter="",
            thread_content=thread_html,
        )

    # --- Reply ---

    async def web_reply(request: Request):
        user_id = _require_auth(request)
        if not user_id:
            return RedirectResponse(url="/web/login", status_code=302)

        if not check_rate_limit(WEB_PAGE_LIMIT, "web", user_id):
            return _htmx_error(429)

        conv_id = request.path_params["conv_id"]
        try:
            conv = get_conversation(db, conv_id)
        except Exception:
            conv = None
        if not conv:
            return _htmx_error(404)

        participants = get_conversation_participants(db, conv_id)
        if user_id not in participants:
            return _htmx_error(403)

        form = await request.form()
        body = form.get("body", "").strip()

        # Validate
        error = None
        if not body:
            error = "Message body cannot be empty."
        elif len(body) > MAX_BODY_LENGTH:
            error = f"Message exceeds {MAX_BODY_LENGTH} character limit."

        if error:
            messages, _ = get_conversation_messages(db, conv_id)
            return _render(
                "partials/thread_view.html",
                user_id=user_id,
                conversation=conv,
                participants=participants,
                messages=[dict(m) for m in messages],
                error=error,
            )

        # Insert reply
        insert_message(db, conv_id, user_id, body)

        # Mark read
        max_seq = get_max_sequence(db, conv_id)
        advance_read_cursor(db, conv_id, user_id, max_seq)

        # Re-render thread with new message
        messages, _ = get_conversation_messages(db, conv_id)
        return _render(
            "partials/thread_view.html",
            user_id=user_id,
            conversation=conv,
            participants=participants,
            messages=[dict(m) for m in messages],
        )

    # --- Compose ---

    async def web_compose_get(request: Request):
        user_id = _require_auth(request)
        if not user_id:
            return RedirectResponse(url="/web/login", status_code=302)

        if not check_rate_limit(WEB_PAGE_LIMIT, "web", user_id):
            if _is_htmx(request):
                return _htmx_error(429)
            return _render_error(429, user_id=user_id)

        all_users = get_all_users(db)
        users = [{"id": u["id"], "display_name": u["display_name"]} for u in all_users if u["id"] != user_id]
        user_projects = get_user_projects(db, user_id)

        html = _render(
            "partials/compose_form.html",
            user_id=user_id,
            users=users,
            projects=user_projects,
            error=None,
            success=None,
            form_to="", form_project="general", form_subject="", form_body="",
        ).body.decode("utf-8")

        if _is_htmx(request):
            return HTMLResponse(html)

        # Full-page fallback
        display_name = _get_user_display_name(db, user_id)
        projects = get_user_projects(db, user_id)
        partners = get_user_conversation_partners(db, user_id)
        return _render(
            "inbox.html",
            user_id=user_id,
            display_name=display_name,
            projects=projects,
            partners=partners,
            project_filter="",
            participant_filter="",
            thread_content=html,
        )

    async def web_compose_post(request: Request):
        user_id = _require_auth(request)
        if not user_id:
            return RedirectResponse(url="/web/login", status_code=302)

        if not check_rate_limit(WEB_PAGE_LIMIT, "web", user_id):
            return _htmx_error(429)

        form = await request.form()
        to = form.get("to", "").strip()
        project = form.get("project", "").strip() or "general"
        subject = form.get("subject", "").strip() or None
        body = form.get("body", "").strip()

        all_users = get_all_users(db)
        users = [{"id": u["id"], "display_name": u["display_name"]} for u in all_users if u["id"] != user_id]
        user_projects = get_user_projects(db, user_id)

        # Validate
        error = None
        if not to:
            error = "Please select a recipient."
        elif to == user_id:
            error = "Cannot send a message to yourself."
        elif get_user(db, to) is None:
            error = f"User '{to}' not found."
        elif not body:
            error = "Message body cannot be empty."
        elif len(body) > MAX_BODY_LENGTH:
            error = f"Message exceeds {MAX_BODY_LENGTH} character limit."

        if error:
            return _render(
                "partials/compose_form.html",
                user_id=user_id,
                users=users,
                projects=user_projects,
                error=error,
                success=None,
                form_to=to, form_project=project, form_subject=subject or "", form_body=body,
            )

        # Create conversation and send
        conv_id = find_or_create_direct_conversation(db, user_id, to, project)
        insert_message(db, conv_id, user_id, body, subject=subject)

        # Mark read
        max_seq = get_max_sequence(db, conv_id)
        advance_read_cursor(db, conv_id, user_id, max_seq)

        # Show the thread
        conv = get_conversation(db, conv_id)
        participants = get_conversation_participants(db, conv_id)
        messages, _ = get_conversation_messages(db, conv_id)

        return _render(
            "partials/thread_view.html",
            user_id=user_id,
            conversation=conv,
            participants=participants,
            messages=[dict(m) for m in messages],
        )

    # --- Health ---

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
        Route("/web/inbox/conversations", web_conversation_list, methods=["GET"]),
        Route("/web/conversation/{conv_id}", web_conversation, methods=["GET"]),
        Route("/web/conversation/{conv_id}/reply", web_reply, methods=["POST"]),
        Route("/web/compose", web_compose_get, methods=["GET"]),
        Route("/web/compose", web_compose_post, methods=["POST"]),
        Route("/web/health", web_health, methods=["GET"]),
    ]
