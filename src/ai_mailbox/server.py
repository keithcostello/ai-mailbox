"""AI Mailbox MCP Server — create_app() factory with OAuth 2.1.

Wires FastMCP tools with OAuth authentication, adds /health and /login
endpoints, and returns a Starlette ASGI app for deployment.
"""

import logging
import sqlite3
from urllib.parse import urlencode, parse_qs

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse as StarletteJSONResponse, HTMLResponse, RedirectResponse
from starlette.routing import Route

from ai_mailbox.config import Config
from ai_mailbox.db.connection import SQLiteDB, PostgresDB
from ai_mailbox.oauth import MailboxOAuthProvider, hash_password, current_user_id
from ai_mailbox.tools.send import tool_send_message
from ai_mailbox.tools.inbox import tool_check_messages
from ai_mailbox.tools.reply import tool_reply_to_message
from ai_mailbox.tools.thread import tool_get_thread
from ai_mailbox.tools.identity import tool_whoami
from ai_mailbox.web import create_web_routes

logger = logging.getLogger(__name__)

# Module-level reference for test access
_mcp_instance: FastMCP | None = None
_oauth_provider: MailboxOAuthProvider | None = None


def _make_sqlite_db() -> SQLiteDB:
    """Create an in-memory SQLite DB with schema."""
    from ai_mailbox.db.schema import ensure_schema_sqlite
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema_sqlite(conn)
    return SQLiteDB(conn)


def _make_postgres_db(database_url: str) -> PostgresDB:
    """Create a PostgreSQL DB connection with schema."""
    from ai_mailbox.db.schema import ensure_schema_postgres
    ensure_schema_postgres(database_url)
    return PostgresDB(database_url)


def _seed_users(db, config: Config) -> None:
    """Upsert users with password hashes."""
    users = [
        ("keith", "Keith", config.keith_password),
        ("amy", "Amy", config.amy_password),
    ]
    for user_id, display_name, password in users:
        if not password:
            continue
        pw_hash = hash_password(password)
        existing = db.fetchone("SELECT id FROM users WHERE id = ?", (user_id,))
        if existing:
            db.execute(
                "UPDATE users SET display_name = ?, password_hash = ? WHERE id = ?",
                (display_name, pw_hash, user_id),
            )
        else:
            # api_key required by schema NOT NULL but no longer used for OAuth
            db.execute(
                "INSERT INTO users (id, display_name, api_key, password_hash) VALUES (?, ?, ?, ?)",
                (user_id, display_name, f"oauth-{user_id}", pw_hash),
            )
    db.commit()
    logger.info(f"Seeded {len([u for u in users if u[2]])} users")


def _get_user_from_request(request: StarletteRequest, provider: MailboxOAuthProvider) -> str | None:
    """Extract user_id from OAuth bearer token in request."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[7:]
    return provider.load_user_from_token(token)


def create_app() -> object:
    """Build and return the ASGI application."""
    global _mcp_instance, _oauth_provider

    config = Config.from_env()
    logging.basicConfig(level=getattr(logging, config.log_level))

    # Database setup
    logger.info("Starting database setup...")
    if config.database_url:
        logger.info("Using PostgreSQL")
        db = _make_postgres_db(config.database_url)
    else:
        logger.info("Using SQLite (in-memory)")
        db = _make_sqlite_db()

    logger.info("Seeding users...")
    _seed_users(db, config)
    logger.info("Database setup complete")

    # OAuth provider
    provider = MailboxOAuthProvider(db=db, jwt_secret=config.jwt_secret)
    _oauth_provider = provider

    # MCP server with OAuth
    issuer_url = f"https://ai-mailbox-server-production.up.railway.app"
    if not config.database_url:
        issuer_url = "http://localhost:8000"  # Local/test mode

    auth_settings = AuthSettings(
        issuer_url=issuer_url,
        resource_server_url=f"{issuer_url}/mcp",
        client_registration_options=ClientRegistrationOptions(enabled=True),
    )
    mcp = FastMCP(
        "ai-mailbox",
        host="0.0.0.0",
        port=config.port,
        auth_server_provider=provider,
        auth=auth_settings,
    )
    _mcp_instance = mcp

    # Transport security for Railway
    if mcp.settings.transport_security:
        mcp.settings.transport_security.allowed_hosts.append("*.up.railway.app:*")
        mcp.settings.transport_security.allowed_hosts.append("*.up.railway.app")
        mcp.settings.transport_security.allowed_origins.append("https://*.up.railway.app")
        mcp.settings.transport_security.allowed_origins.append("https://*.up.railway.app:*")

    # --- MCP Tools (user identity from OAuth token via contextvars) ---

    def _get_user() -> str:
        """Get authenticated user_id from OAuth context. Logs for isolation audit."""
        uid = current_user_id.get("unknown")
        logger.info(f"Tool call: authenticated as user={uid}")
        return uid

    @mcp.tool()
    def send_message(to: str, body: str, project: str = "general", subject: str = "") -> dict:
        """Send a message to another user. Use project to organize by topic."""
        uid = _get_user()
        logger.info(f"send_message: from={uid} to={to} project={project}")
        return tool_send_message(
            db, user_id=uid, to=to, body=body,
            project=project, subject=subject or None,
        )

    @mcp.tool()
    def check_messages(project: str = "", unread_only: bool = True) -> dict:
        """Check your inbox. Returns messages and marks them as read."""
        uid = _get_user()
        logger.info(f"check_messages: user={uid} project={project or 'all'}")
        return tool_check_messages(
            db, user_id=uid,
            project=project or None, unread_only=unread_only,
        )

    @mcp.tool()
    def reply_to_message(message_id: str, body: str) -> dict:
        """Reply to a specific message. Inherits project and thread."""
        uid = _get_user()
        logger.info(f"reply_to_message: user={uid} message_id={message_id}")
        return tool_reply_to_message(
            db, user_id=uid, message_id=message_id, body=body,
        )

    @mcp.tool()
    def get_thread(message_id: str) -> dict:
        """Get the full conversation thread from any message in it."""
        uid = _get_user()
        logger.info(f"get_thread: user={uid} message_id={message_id}")
        return tool_get_thread(
            db, user_id=uid, message_id=message_id,
        )

    @mcp.tool()
    def whoami() -> dict:
        """Identity check. Returns your user info and unread counts per project."""
        uid = _get_user()
        logger.info(f"whoami: user={uid}")
        return tool_whoami(db, user_id=uid)

    # --- Login page ---

    async def login_get(request: StarletteRequest):
        """Render login form."""
        params = request.query_params
        return HTMLResponse(provider.login_page_html(
            client_id=params.get("client_id", ""),
            code_challenge=params.get("code_challenge", ""),
            redirect_uri=params.get("redirect_uri", ""),
            state=params.get("state", ""),
            scopes=params.get("scopes", ""),
        ))

    async def login_post(request: StarletteRequest):
        """Handle login form submission."""
        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")
        client_id = form.get("client_id", "")
        code_challenge = form.get("code_challenge", "")
        redirect_uri = form.get("redirect_uri", "")
        state = form.get("state", "")
        scopes = form.get("scopes", "")

        user_id = provider.authenticate_user(username, password)
        if user_id is None:
            return HTMLResponse(
                "<html><body><h2>Login failed</h2><p>Invalid username or password.</p>"
                "<a href='javascript:history.back()'>Try again</a></body></html>",
                status_code=401,
            )

        # Create authorization code
        code = provider.create_authorization_code(
            client_id=client_id,
            user_id=user_id,
            code_challenge=code_challenge,
            redirect_uri=redirect_uri,
            scopes=scopes.split(",") if scopes else [],
        )

        # Redirect back to client with auth code
        redirect_params = {"code": code}
        if state:
            redirect_params["state"] = state
        return RedirectResponse(
            url=f"{redirect_uri}?{urlencode(redirect_params)}",
            status_code=302,
        )

    # --- Health endpoint ---

    async def health(request: StarletteRequest):
        row = db.fetchone("SELECT COUNT(*) as cnt FROM users")
        user_count = row["cnt"] if row else 0
        return StarletteJSONResponse({
            "status": "healthy",
            "version": "0.2.0",
            "user_count": user_count,
            "auth": "oauth2.1",
        })

    # Web UI routes (Jinja2 + HTMX + Tailwind)
    web_routes = create_web_routes(db, provider, config.jwt_secret)

    mcp._custom_starlette_routes = [
        Route("/health", health),
        Route("/login", login_get, methods=["GET"]),
        Route("/login", login_post, methods=["POST"]),
    ] + web_routes

    # Build ASGI app
    app = mcp.streamable_http_app()

    # CORS
    from starlette.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app
