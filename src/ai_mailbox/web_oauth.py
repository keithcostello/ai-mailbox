"""GitHub OAuth routes for web UI registration and login.

Handles the OAuth 2.0 authorization code flow for GitHub.
MCP clients continue to use password-based auth via MailboxOAuthProvider.
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import httpx
import jwt
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from ai_mailbox.config import Config
    from ai_mailbox.db.connection import DBConnection
    from ai_mailbox.oauth import MailboxOAuthProvider

logger = logging.getLogger(__name__)

_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"
_GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

_HANDLE_RE = re.compile(r"^[a-z0-9_-]{2,30}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _suggest_handle(email: str) -> str:
    """Suggest a handle from an email address."""
    local_part = email.split("@")[0] if "@" in email else email
    clean = "".join(c if c.isalnum() or c in "-_" else "" for c in local_part.lower())
    return clean[:30] if clean else "user"


def create_oauth_user(
    db: DBConnection,
    *,
    user_id: str,
    email: str,
    name: str,
    avatar_url: str | None,
    provider: str,
) -> str:
    """Create a new OAuth user with an explicit user_id (handle). Returns user_id."""
    db.execute(
        """INSERT INTO users (id, display_name, api_key, password_hash, email, auth_provider, avatar_url)
           VALUES (?, ?, ?, '', ?, ?, ?)""",
        (user_id, name, f"oauth-{user_id}", email, provider, avatar_url),
    )
    db.commit()
    return user_id


def find_existing_oauth_user(db: DBConnection, email: str, provider: str) -> str | None:
    """Find existing user by email+provider. Returns user_id or None."""
    existing = db.fetchone(
        "SELECT id FROM users WHERE email = ? AND auth_provider = ?",
        (email, provider),
    )
    if not existing:
        return None
    # Update name/avatar on each login
    return existing["id"]


def update_oauth_user_profile(db: DBConnection, user_id: str, name: str, avatar_url: str | None) -> None:
    """Update display name and avatar for a returning OAuth user."""
    db.execute(
        "UPDATE users SET display_name = ?, avatar_url = ? WHERE id = ?",
        (name, avatar_url, user_id),
    )
    db.commit()


# Keep for backward compat with tests
def find_or_create_oauth_user(
    db: DBConnection,
    *,
    email: str,
    name: str,
    avatar_url: str | None,
    provider: str,
) -> str:
    """Find existing user by email+provider, or create with auto-generated ID."""
    uid = find_existing_oauth_user(db, email, provider)
    if uid:
        update_oauth_user_profile(db, uid, name, avatar_url)
        return uid

    # Auto-generate ID (used by tests, not by live OAuth flow)
    if provider == "github":
        prefix = "gh"
    else:
        prefix = provider[:2]
    local_part = email.split("@")[0] if "@" in email else email
    clean = "".join(c if c.isalnum() or c == "-" else "" for c in local_part.lower())
    if not clean:
        clean = "user"
    base_id = f"{prefix}-{clean}"
    candidate = base_id
    suffix = 2
    while db.fetchone("SELECT id FROM users WHERE id = ?", (candidate,)):
        candidate = f"{base_id}-{suffix}"
        suffix += 1

    return create_oauth_user(
        db, user_id=candidate, email=email, name=name,
        avatar_url=avatar_url, provider=provider,
    )


def check_invite(db: DBConnection, email: str, provider: str) -> bool:
    """Check if an email is invited or already a registered user."""
    existing = db.fetchone(
        "SELECT id FROM users WHERE email = ? AND auth_provider = ?",
        (email, provider),
    )
    if existing:
        return True
    invite = db.fetchone("SELECT email FROM user_invites WHERE email = ?", (email,))
    return invite is not None


def mark_invite_used(db: DBConnection, email: str) -> None:
    """Mark an invite as used."""
    db.execute(
        "UPDATE user_invites SET used_at = ? WHERE email = ? AND used_at IS NULL",
        (_now(), email),
    )
    db.commit()


def validate_handle(db: DBConnection, handle: str) -> str | None:
    """Validate a handle. Returns error message or None if valid."""
    if not handle:
        return "Username is required."
    if not _HANDLE_RE.match(handle):
        return "Lowercase letters, numbers, hyphens, underscores only. 2-30 characters."
    if db.fetchone("SELECT id FROM users WHERE id = ?", (handle,)):
        return f"'{handle}' is already taken."
    return None


def create_oauth_routes(
    db: DBConnection,
    provider: MailboxOAuthProvider,
    config: Config,
    jwt_secret: str,
) -> list[Route]:
    """Create OAuth web routes for GitHub login."""

    from jinja2 import Environment, FileSystemLoader
    from pathlib import Path
    _tmpl_dir = Path(__file__).parent / "templates"
    _jinja = Environment(loader=FileSystemLoader(str(_tmpl_dir)), autoescape=True)

    # In-memory state store for CSRF protection
    _pending_states: dict[str, float] = {}  # state -> expiry timestamp

    # Pending registrations: token -> {email, name, avatar_url, provider, expires}
    _pending_registrations: dict[str, dict] = {}

    def _callback_url(request: Request) -> str:
        """Build the OAuth callback URL, forcing HTTPS behind reverse proxies."""
        url = str(request.url_for("oauth_callback"))
        if url.startswith("http://") and "localhost" not in url:
            url = "https://" + url[7:]
        return url

    def _create_session(user_id: str, redirect_to: str = "/web/inbox") -> RedirectResponse:
        token = jwt.encode(
            {"sub": user_id, "iat": int(time.time()), "exp": int(time.time()) + 86400},
            jwt_secret,
            algorithm="HS256",
        )
        response = RedirectResponse(url=redirect_to, status_code=302)
        response.set_cookie(
            key="session", value=token, httponly=True,
            samesite="lax", path="/web", max_age=86400,
        )
        response.delete_cookie(key="oauth_state", path="/web")
        return response

    async def github_initiate(request: Request):
        """Redirect user to GitHub for authorization."""
        state = secrets.token_urlsafe(32)
        _pending_states[state] = time.time() + 600

        params = {
            "client_id": config.github_client_id,
            "redirect_uri": _callback_url(request),
            "scope": "user:email read:user",
            "state": state,
        }
        response = RedirectResponse(
            url=f"{_GITHUB_AUTHORIZE_URL}?{urlencode(params)}",
            status_code=302,
        )
        response.set_cookie(
            key="oauth_state", value=state, httponly=True,
            samesite="lax", path="/web", max_age=600,
        )
        return response

    async def oauth_callback(request: Request):
        """Handle GitHub OAuth callback -- exchange code, create/lookup user."""
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        cookie_state = request.cookies.get("oauth_state")

        if not code or not state:
            return RedirectResponse(url="/web/login?error=oauth_failed", status_code=302)
        if state != cookie_state or state not in _pending_states:
            return RedirectResponse(url="/web/login?error=oauth_failed", status_code=302)
        if _pending_states.get(state, 0) < time.time():
            _pending_states.pop(state, None)
            return RedirectResponse(url="/web/login?error=oauth_failed", status_code=302)
        _pending_states.pop(state, None)

        # Exchange code for access token
        try:
            token_resp = httpx.post(
                _GITHUB_TOKEN_URL,
                data={
                    "client_id": config.github_client_id,
                    "client_secret": config.github_client_secret,
                    "code": code,
                    "redirect_uri": _callback_url(request),
                },
                headers={"Accept": "application/json"},
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                return RedirectResponse(url="/web/login?error=oauth_failed", status_code=302)
        except Exception:
            logger.exception("GitHub token exchange failed")
            return RedirectResponse(url="/web/login?error=oauth_failed", status_code=302)

        # Fetch user info
        try:
            headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
            user_resp = httpx.get(_GITHUB_USER_URL, headers=headers)
            user_resp.raise_for_status()
            user_data = user_resp.json()

            emails_resp = httpx.get(_GITHUB_EMAILS_URL, headers=headers)
            emails_resp.raise_for_status()
            emails = emails_resp.json()
            primary_email = next(
                (e["email"] for e in emails if e.get("primary") and e.get("verified")),
                None,
            )
            if not primary_email:
                primary_email = next((e["email"] for e in emails if e.get("verified")), None)
            if not primary_email:
                return RedirectResponse(url="/web/login?error=no_email", status_code=302)
        except Exception:
            logger.exception("GitHub user info fetch failed")
            return RedirectResponse(url="/web/login?error=oauth_failed", status_code=302)

        # Invite check
        if config.invite_only:
            if not check_invite(db, primary_email, "github"):
                return RedirectResponse(url="/web/login?error=not_invited", status_code=302)
            mark_invite_used(db, primary_email)

        name = user_data.get("name") or user_data.get("login", "GitHub User")
        avatar_url = user_data.get("avatar_url")

        # Returning user? Log in directly.
        existing_uid = find_existing_oauth_user(db, primary_email, "github")
        if existing_uid:
            update_oauth_user_profile(db, existing_uid, name, avatar_url)
            return _create_session(existing_uid)

        # New user -- redirect to handle picker
        reg_token = secrets.token_urlsafe(32)
        _pending_registrations[reg_token] = {
            "email": primary_email,
            "name": name,
            "avatar_url": avatar_url,
            "provider": "github",
            "expires": time.time() + 600,
        }
        return RedirectResponse(url=f"/web/oauth/pick-handle?token={reg_token}", status_code=302)

    async def pick_handle_get(request: Request):
        """Show the 'pick your username' page."""
        reg_token = request.query_params.get("token", "")
        reg = _pending_registrations.get(reg_token)
        if not reg or reg["expires"] < time.time():
            return RedirectResponse(url="/web/login?error=oauth_failed", status_code=302)

        suggested = _suggest_handle(reg["email"])
        tmpl = _jinja.get_template("pick_handle.html")
        return HTMLResponse(tmpl.render(
            name=reg["name"],
            suggested=suggested,
            token=reg_token,
            error=None,
            user_id=None,
        ))

    async def pick_handle_post(request: Request):
        """Create the user with the chosen handle."""
        form = await request.form()
        reg_token = form.get("token", "")
        handle = form.get("handle", "").strip().lower()

        reg = _pending_registrations.get(reg_token)
        if not reg or reg["expires"] < time.time():
            return RedirectResponse(url="/web/login?error=oauth_failed", status_code=302)

        error = validate_handle(db, handle)
        if error:
            tmpl = _jinja.get_template("pick_handle.html")
            return HTMLResponse(tmpl.render(
                name=reg["name"],
                suggested=handle,
                token=reg_token,
                error=error,
                user_id=None,
            ))

        # Create user with chosen handle
        create_oauth_user(
            db,
            user_id=handle,
            email=reg["email"],
            name=reg["name"],
            avatar_url=reg["avatar_url"],
            provider=reg["provider"],
        )
        _pending_registrations.pop(reg_token, None)

        return _create_session(handle)

    return [
        Route("/web/oauth/github", github_initiate, methods=["GET"]),
        Route("/web/oauth/callback", oauth_callback, methods=["GET"], name="oauth_callback"),
        Route("/web/oauth/pick-handle", pick_handle_get, methods=["GET"]),
        Route("/web/oauth/pick-handle", pick_handle_post, methods=["POST"]),
    ]
