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

# Per-request cache for is_ai_user DB lookups (avoids N+1 in thread view)
_ai_user_cache: dict[str, bool] = {}


def _is_ai_user(user_id: str) -> bool:
    """Check if user is an agent by user_type field. Cached per-request."""
    return _ai_user_cache.get(user_id, False)


# Register Jinja2 globals and filters
_jinja_env.globals["is_ai_user"] = _is_ai_user
_jinja_env.filters["markdown"] = lambda text: Markup(render_markdown(text)) if text else Markup("")


def _pretty_json(text: str) -> str:
    """Format JSON string with indentation. Returns original if not valid JSON."""
    import json
    try:
        parsed = json.loads(text)
        return json.dumps(parsed, indent=2)
    except (json.JSONDecodeError, TypeError):
        return text


_jinja_env.filters["pretty_json"] = _pretty_json


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


def create_web_routes(db: DBConnection, provider: MailboxOAuthProvider, jwt_secret: str, *, github_oauth: bool = False) -> list[Route]:
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
        search_messages,
        set_archive,
    )

    # --- Auth helpers ---

    def _require_auth(request):
        """Returns user_id or None. Caller should redirect if None."""
        return _get_session_user(request, jwt_secret)

    def _is_htmx(request):
        """Check if request is from HTMX."""
        return request.headers.get("HX-Request") == "true"

    def _refresh_ai_user_cache():
        """Reload the AI user cache from DB. Call once per request cycle."""
        _ai_user_cache.clear()
        for u in get_all_users(db):
            if u.get("user_type") == "agent":
                _ai_user_cache[u["id"]] = True

    # --- Login / Logout ---

    _OAUTH_ERRORS = {
        "not_invited": "Your email is not on the invite list. Contact an admin for access.",
        "oauth_failed": "Authentication failed. Please try again.",
        "no_email": "Could not retrieve a verified email from your account.",
    }

    async def web_login_get(request: Request):
        user_id = _require_auth(request)
        if user_id:
            return RedirectResponse(url="/web/inbox", status_code=302)
        error_code = request.query_params.get("error", "")
        error = _OAUTH_ERRORS.get(error_code)
        return _render("login.html", error=error, user_id=None, github_oauth=github_oauth)

    async def web_login_post(request: Request):
        ip = _client_ip(request)
        if not check_rate_limit(WEB_LOGIN_LIMIT, "login", ip):
            return _render(
                "login.html",
                error="Too many login attempts. Try again in 1 minute.",
                user_id=None,
                github_oauth=github_oauth,
                status_code=429,
            )

        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")

        user_id = provider.authenticate_user(username, password)
        if user_id is None:
            return _render("login.html", error="Invalid username or password", user_id=None, github_oauth=github_oauth)

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
        include_archived = request.query_params.get("archived", "") == "true"
        page = int(request.query_params.get("page", "1"))
        if page < 1:
            page = 1
        offset = (page - 1) * INBOX_PAGE_SIZE

        conversations, has_more = get_inbox_paginated(
            db, user_id,
            project=project_filter or None,
            limit=INBOX_PAGE_SIZE, offset=offset,
            include_archived=include_archived,
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

        # Check archive state
        cp_row = db.fetchone(
            "SELECT archived_at FROM conversation_participants WHERE conversation_id = ? AND user_id = ?",
            (conv_id, user_id),
        )
        is_archived = cp_row["archived_at"] is not None if cp_row else False

        _refresh_ai_user_cache()

        thread_html = _render(
            "partials/thread_view.html",
            user_id=user_id,
            conversation=conv,
            participants=participants,
            messages=[dict(m) for m in messages],
            is_archived=is_archived,
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

    # --- Search ---

    async def web_search(request: Request):
        user_id = _require_auth(request)
        if not user_id:
            return RedirectResponse(url="/web/login", status_code=302)

        if not check_rate_limit(WEB_PAGE_LIMIT, "web", user_id):
            return _htmx_error(429)

        query = request.query_params.get("q", "").strip()
        if not query:
            return _render("partials/empty_state.html", user_id=user_id)

        results = search_messages(db, user_id, query, limit=20)
        for r in results:
            body = r["body"]
            r["body_preview"] = body[:200] + ("..." if len(body) > 200 else "")

        return _render(
            "partials/search_results.html",
            user_id=user_id,
            query=query,
            results=results,
        )

    # --- Message list partial (for thread polling) ---

    async def web_message_list(request: Request):
        user_id = _require_auth(request)
        if not user_id:
            return HTMLResponse("", status_code=401)

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

        messages, _ = get_conversation_messages(db, conv_id)

        # Auto-mark-read on poll
        max_seq = get_max_sequence(db, conv_id)
        if max_seq > 0:
            advance_read_cursor(db, conv_id, user_id, max_seq)

        return _render(
            "partials/message_list.html",
            user_id=user_id,
            messages=[dict(m) for m in messages],
        )

    # --- Archive ---

    async def web_archive(request: Request):
        user_id = _require_auth(request)
        if not user_id:
            return RedirectResponse(url="/web/login", status_code=302)

        if not check_rate_limit(WEB_PAGE_LIMIT, "web", user_id):
            return _htmx_error(429)

        conv_id = request.path_params["conv_id"]
        conv = get_conversation(db, conv_id)
        if not conv:
            return _htmx_error(404)

        participants = get_conversation_participants(db, conv_id)
        if user_id not in participants:
            return _htmx_error(403)

        # Toggle archive state
        cp_row = db.fetchone(
            "SELECT archived_at FROM conversation_participants WHERE conversation_id = ? AND user_id = ?",
            (conv_id, user_id),
        )
        currently_archived = cp_row["archived_at"] is not None if cp_row else False
        set_archive(db, conv_id, user_id, not currently_archived)

        # Re-render the thread
        messages, _ = get_conversation_messages(db, conv_id)
        max_seq = get_max_sequence(db, conv_id)
        if max_seq > 0:
            advance_read_cursor(db, conv_id, user_id, max_seq)

        _refresh_ai_user_cache()

        return _render(
            "partials/thread_view.html",
            user_id=user_id,
            conversation=conv,
            participants=participants,
            messages=[dict(m) for m in messages],
            is_archived=not currently_archived,
        )

    # --- User directory ---

    async def web_users(request: Request):
        user_id = _require_auth(request)
        if not user_id:
            return RedirectResponse(url="/web/login", status_code=302)

        if not check_rate_limit(WEB_PAGE_LIMIT, "web", user_id):
            return _render_error(429, user_id=user_id)

        display_name = _get_user_display_name(db, user_id)
        all_users = get_all_users(db)
        users = []
        now = datetime.now(timezone.utc)
        for u in all_users:
            last_seen = u.get("last_seen")
            online = False
            if last_seen:
                try:
                    seen_dt = datetime.fromisoformat(last_seen)
                    if seen_dt.tzinfo is None:
                        seen_dt = seen_dt.replace(tzinfo=timezone.utc)
                    from datetime import timedelta
                    online = (now - seen_dt) < timedelta(minutes=5)
                except (ValueError, TypeError):
                    pass
            users.append({
                "id": u["id"],
                "display_name": u["display_name"],
                "user_type": u.get("user_type", "human"),
                "last_seen": last_seen,
                "online": online,
            })

        return _render(
            "users.html",
            user_id=user_id,
            display_name=display_name,
            users=users,
        )

    # --- Settings ---

    async def web_settings_get(request: Request):
        user_id = _require_auth(request)
        if not user_id:
            return RedirectResponse(url="/web/login", status_code=302)

        if not check_rate_limit(WEB_PAGE_LIMIT, "web", user_id):
            return _render_error(429, user_id=user_id)

        display_name = _get_user_display_name(db, user_id)
        user = db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
        return _render(
            "settings.html",
            user_id=user_id,
            display_name=display_name,
            user=dict(user) if user else {},
        )

    async def web_settings_post(request: Request):
        user_id = _require_auth(request)
        if not user_id:
            return RedirectResponse(url="/web/login", status_code=302)

        if not check_rate_limit(WEB_PAGE_LIMIT, "web", user_id):
            return _render_error(429, user_id=user_id)

        form = await request.form()
        new_name = form.get("display_name", "").strip()

        user = db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
        user_dict = dict(user) if user else {}

        if not new_name or len(new_name) > 100:
            return _render(
                "settings.html",
                user_id=user_id,
                display_name=user_dict.get("display_name", user_id),
                user=user_dict,
                error="Invalid display name.",
            )

        db.execute(
            "UPDATE users SET display_name = ? WHERE id = ?",
            (new_name, user_id),
        )
        db.commit()

        # Re-read updated user
        user = db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
        user_dict = dict(user) if user else {}
        return _render(
            "settings.html",
            user_id=user_id,
            display_name=new_name,
            user=user_dict,
            success=True,
        )

    # --- Health ---

    async def web_health(request: Request):
        row = db.fetchone("SELECT COUNT(*) as cnt FROM users")
        user_count = row["cnt"] if row else 0
        health = {
            "status": "healthy",
            "version": "0.6.0",
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
        Route("/web/conversation/{conv_id}/archive", web_archive, methods=["POST"]),
        Route("/web/compose", web_compose_get, methods=["GET"]),
        Route("/web/compose", web_compose_post, methods=["POST"]),
        Route("/web/search", web_search, methods=["GET"]),
        Route("/web/conversation/{conv_id}/messages", web_message_list, methods=["GET"]),
        Route("/web/users", web_users, methods=["GET"]),
        Route("/web/settings", web_settings_get, methods=["GET"]),
        Route("/web/settings", web_settings_post, methods=["POST"]),
        Route("/web/health", web_health, methods=["GET"]),
    ]
