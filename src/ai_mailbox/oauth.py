"""OAuth 2.1 provider for AI Mailbox.

Implements the MCP SDK's OAuthAuthorizationServerProvider protocol.
The SDK handles all HTTP endpoints (discovery, authorize, token, register).
We provide storage and user authentication logic.
"""

from __future__ import annotations

import contextvars
import hashlib
import html
import json
import secrets
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlencode

# Context variable set during token validation, read by tools
current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_user_id", default=None)

import logging

import bcrypt
import jwt

logger = logging.getLogger(__name__)

from mcp.server.auth.provider import (
    OAuthAuthorizationServerProvider,
    AuthorizationParams,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from mcp.server.auth.middleware.bearer_auth import AccessToken

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection


def _parse_scopes(scopes_str: str | None) -> list[str]:
    """Parse scopes from DB. Handles both JSON array and comma-separated formats."""
    if not scopes_str:
        return []
    try:
        parsed = json.loads(scopes_str)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return [s.strip() for s in scopes_str.split(",") if s.strip()]


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, pw_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode(), pw_hash.encode())


@dataclass
class AuthCode:
    """Stored authorization code."""
    code: str
    client_id: str
    user_id: str
    code_challenge: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    scopes: list[str]
    expires_at: float


class MailboxOAuthProvider:
    """OAuth provider backed by the mailbox database.

    Implements the OAuthAuthorizationServerProvider protocol.
    The MCP SDK calls these methods from its auto-generated HTTP handlers.
    """

    def __init__(self, *, db: DBConnection, jwt_secret: str):
        self.db = db
        self.jwt_secret = jwt_secret

    # --- Token helpers (used by tools to identify users) ---

    def create_user_token(
        self, *, user_id: str, client_id: str, expires_in: int = 3600
    ) -> str:
        """Create a JWT access token encoding user_id."""
        now = int(time.time())
        payload = {
            "sub": user_id,
            "client_id": client_id,
            "iat": now,
            "exp": now + expires_in,
        }
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")

    def load_user_from_token(self, token: str) -> str | None:
        """Decode a JWT and return the user_id, or None if invalid/expired."""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            return payload.get("sub")
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return None

    # --- OAuthAuthorizationServerProvider protocol ---

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        row = self.db.fetchone(
            "SELECT client_info FROM oauth_clients WHERE client_id = ?",
            (client_id,),
        )
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate_json(row["client_info"])

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        client_id = client_info.client_id or secrets.token_urlsafe(32)
        client_info.client_id = client_id
        self.db.execute(
            "INSERT INTO oauth_clients (client_id, client_info) VALUES (?, ?)",
            (client_id, client_info.model_dump_json()),
        )
        self.db.commit()

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Return URL for the login page. User authenticates there."""
        # Build login page URL with OAuth params encoded
        login_params = {
            "client_id": client.client_id,
            "code_challenge": params.code_challenge,
            "redirect_uri": str(params.redirect_uri),
            "state": params.state or "",
            "scopes": ",".join(params.scopes or []),
            "redirect_uri_explicit": "1" if params.redirect_uri_provided_explicitly else "0",
        }
        return f"/login?{urlencode(login_params)}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthCode | None:
        row = self.db.fetchone(
            "SELECT * FROM oauth_codes WHERE code = ? AND client_id = ?",
            (authorization_code, client.client_id),
        )
        if row is None:
            return None
        if row["expires_at"] and float(row["expires_at"]) < time.time():
            return None
        return AuthCode(
            code=row["code"],
            client_id=row["client_id"],
            user_id=row["user_id"],
            code_challenge=row["code_challenge"],
            redirect_uri=row["redirect_uri"],
            redirect_uri_provided_explicitly=True,
            scopes=_parse_scopes(row["scopes"]),
            expires_at=float(row["expires_at"]),
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthCode
    ) -> OAuthToken:
        """Exchange auth code for access + refresh tokens."""
        access_token = self.create_user_token(
            user_id=authorization_code.user_id,
            client_id=authorization_code.client_id,
            expires_in=3600,
        )
        refresh_token = secrets.token_urlsafe(48)

        # Store token mapping
        self.db.execute(
            "INSERT INTO oauth_tokens (token, client_id, user_id, scopes, expires_at, refresh_token) VALUES (?, ?, ?, ?, ?, ?)",
            (
                access_token,
                authorization_code.client_id,
                authorization_code.user_id,
                json.dumps(authorization_code.scopes),
                int(time.time()) + 3600,
                refresh_token,
            ),
        )
        # Delete used auth code
        self.db.execute(
            "DELETE FROM oauth_codes WHERE code = ?", (authorization_code.code,)
        )
        self.db.commit()

        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=3600,
            refresh_token=refresh_token,
            scope=" ".join(authorization_code.scopes),
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Validate access token. Called by SDK middleware on every MCP request."""
        user_id = self.load_user_from_token(token)
        if user_id is None:
            return None
        # Set context var so tools can read the authenticated user
        current_user_id.set(user_id)
        # Look up stored token for client_id
        row = self.db.fetchone(
            "SELECT * FROM oauth_tokens WHERE token = ?", (token,)
        )
        client_id = row["client_id"] if row else "unknown"
        logger.info(f"OAuth: authenticated user={user_id} client={client_id}")
        scopes = _parse_scopes(row["scopes"]) if row else []
        expires_at = row["expires_at"] if row else None

        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=expires_at,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> str | None:
        row = self.db.fetchone(
            "SELECT refresh_token FROM oauth_tokens WHERE refresh_token = ? AND client_id = ?",
            (refresh_token, client.client_id),
        )
        return row["refresh_token"] if row else None

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str, scopes: list[str]
    ) -> OAuthToken:
        """Issue new tokens from refresh token."""
        # Find the old token record
        row = self.db.fetchone(
            "SELECT * FROM oauth_tokens WHERE refresh_token = ? AND client_id = ?",
            (refresh_token, client.client_id),
        )
        if row is None:
            raise ValueError("Invalid refresh token")

        user_id = row["user_id"]
        new_access = self.create_user_token(
            user_id=user_id, client_id=client.client_id, expires_in=3600
        )
        new_refresh = secrets.token_urlsafe(48)

        # Replace old token
        self.db.execute("DELETE FROM oauth_tokens WHERE refresh_token = ?", (refresh_token,))
        self.db.execute(
            "INSERT INTO oauth_tokens (token, client_id, user_id, scopes, expires_at, refresh_token) VALUES (?, ?, ?, ?, ?, ?)",
            (new_access, client.client_id, user_id, json.dumps(scopes), int(time.time()) + 3600, new_refresh),
        )
        self.db.commit()

        return OAuthToken(
            access_token=new_access,
            token_type="Bearer",
            expires_in=3600,
            refresh_token=new_refresh,
            scope=" ".join(scopes),
        )

    async def revoke_token(self, token) -> None:
        """Revoke an access or refresh token."""
        if isinstance(token, str):
            self.db.execute("DELETE FROM oauth_tokens WHERE token = ? OR refresh_token = ?", (token, token))
        else:
            self.db.execute("DELETE FROM oauth_tokens WHERE token = ?", (token.token,))
        self.db.commit()

    # --- Login page + authentication ---

    def authenticate_user(self, username: str, password: str) -> str | None:
        """Validate username/password against users table. Returns user_id or None."""
        row = self.db.fetchone(
            "SELECT id, password_hash FROM users WHERE id = ?", (username,)
        )
        if row is None or not row["password_hash"]:
            return None
        if verify_password(password, row["password_hash"]):
            return row["id"]
        return None

    def create_authorization_code(
        self,
        *,
        client_id: str,
        user_id: str,
        code_challenge: str,
        redirect_uri: str,
        scopes: list[str],
    ) -> str:
        """Create and store an authorization code."""
        code = secrets.token_urlsafe(48)
        expires_at = time.time() + 300  # 5 minutes

        self.db.execute(
            "INSERT INTO oauth_codes (code, client_id, user_id, code_challenge, redirect_uri, scopes, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, client_id, user_id, code_challenge, redirect_uri, json.dumps(scopes), expires_at),
        )
        self.db.commit()
        return code

    def login_page_html(self, client_id: str, code_challenge: str, redirect_uri: str, state: str, scopes: str) -> str:
        """Render the login form HTML."""
        return f"""<!DOCTYPE html>
<html>
<head><title>AI Mailbox Login</title>
<style>
body {{ font-family: sans-serif; max-width: 400px; margin: 80px auto; }}
input {{ width: 100%; padding: 10px; margin: 8px 0; box-sizing: border-box; }}
button {{ width: 100%; padding: 12px; background: #333; color: white; border: none; cursor: pointer; }}
.error {{ color: red; }}
</style></head>
<body>
<h2>AI Mailbox Login</h2>
<form method="POST" action="/login">
<input type="hidden" name="client_id" value="{html.escape(client_id)}">
<input type="hidden" name="code_challenge" value="{html.escape(code_challenge)}">
<input type="hidden" name="redirect_uri" value="{html.escape(redirect_uri)}">
<input type="hidden" name="state" value="{html.escape(state)}">
<input type="hidden" name="scopes" value="{html.escape(scopes)}">
<input type="text" name="username" placeholder="Username" required autofocus>
<input type="password" name="password" placeholder="Password" required>
<button type="submit">Sign In</button>
</form>
</body></html>"""
