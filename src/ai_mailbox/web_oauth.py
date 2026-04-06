"""GitHub OAuth routes for web UI registration and login.

Handles the OAuth 2.0 authorization code flow for GitHub.
MCP clients continue to use password-based auth via MailboxOAuthProvider.
"""

from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import httpx
import jwt
from starlette.requests import Request
from starlette.responses import RedirectResponse
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_user_id(db: DBConnection, email: str, provider: str) -> str:
    """Generate a human-readable user_id from email/provider, resolving collisions."""
    if provider == "github":
        prefix = "gh"
    else:
        prefix = provider[:2]

    # Use email prefix (before @)
    local_part = email.split("@")[0] if "@" in email else email
    # Sanitize: keep alphanumeric and hyphens
    clean = "".join(c if c.isalnum() or c == "-" else "" for c in local_part.lower())
    if not clean:
        clean = "user"

    base_id = f"{prefix}-{clean}"
    candidate = base_id
    suffix = 2
    while db.fetchone("SELECT id FROM users WHERE id = ?", (candidate,)):
        candidate = f"{base_id}-{suffix}"
        suffix += 1
    return candidate


def find_or_create_oauth_user(
    db: DBConnection,
    *,
    email: str,
    name: str,
    avatar_url: str | None,
    provider: str,
) -> str:
    """Find existing user by email+provider, or create new one. Returns user_id."""
    existing = db.fetchone(
        "SELECT id FROM users WHERE email = ? AND auth_provider = ?",
        (email, provider),
    )
    if existing:
        db.execute(
            "UPDATE users SET display_name = ?, avatar_url = ? WHERE id = ?",
            (name, avatar_url, existing["id"]),
        )
        db.commit()
        return existing["id"]

    user_id = _generate_user_id(db, email, provider)
    db.execute(
        """INSERT INTO users (id, display_name, api_key, password_hash, email, auth_provider, avatar_url)
           VALUES (?, ?, ?, '', ?, ?, ?)""",
        (user_id, name, f"oauth-{user_id}", email, provider, avatar_url),
    )
    db.commit()
    return user_id


def check_invite(db: DBConnection, email: str, provider: str) -> bool:
    """Check if an email is invited or already a registered user."""
    # Already registered? Always allowed.
    existing = db.fetchone(
        "SELECT id FROM users WHERE email = ? AND auth_provider = ?",
        (email, provider),
    )
    if existing:
        return True
    # Check invite table
    invite = db.fetchone("SELECT email FROM user_invites WHERE email = ?", (email,))
    return invite is not None


def mark_invite_used(db: DBConnection, email: str) -> None:
    """Mark an invite as used."""
    db.execute(
        "UPDATE user_invites SET used_at = ? WHERE email = ? AND used_at IS NULL",
        (_now(), email),
    )
    db.commit()


def create_oauth_routes(
    db: DBConnection,
    provider: MailboxOAuthProvider,
    config: Config,
    jwt_secret: str,
) -> list[Route]:
    """Create OAuth web routes for GitHub login."""

    # In-memory state store for CSRF protection
    _pending_states: dict[str, float] = {}  # state -> expiry timestamp

    async def github_initiate(request: Request):
        """Redirect user to GitHub for authorization."""
        state = secrets.token_urlsafe(32)
        _pending_states[state] = time.time() + 600  # 10 minute expiry

        params = {
            "client_id": config.github_client_id,
            "redirect_uri": str(request.url_for("oauth_callback")),
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

        # Validate state
        if not code or not state:
            return RedirectResponse(url="/web/login?error=oauth_failed", status_code=302)

        if state != cookie_state or state not in _pending_states:
            return RedirectResponse(url="/web/login?error=oauth_failed", status_code=302)

        # Check expiry and clean up
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
                    "redirect_uri": str(request.url_for("oauth_callback")),
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

        # Create or update user
        name = user_data.get("name") or user_data.get("login", "GitHub User")
        avatar_url = user_data.get("avatar_url")
        user_id = find_or_create_oauth_user(
            db, email=primary_email, name=name,
            avatar_url=avatar_url, provider="github",
        )

        # Create session
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
        response.delete_cookie(key="oauth_state", path="/web")
        return response

    return [
        Route("/web/oauth/github", github_initiate, methods=["GET"]),
        Route("/web/oauth/callback", oauth_callback, methods=["GET"], name="oauth_callback"),
    ]
