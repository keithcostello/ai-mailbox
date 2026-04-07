"""AI Mailbox MCP Server — create_app() factory with OAuth 2.1.

Wires FastMCP tools with OAuth authentication, adds /health and /login
endpoints, and returns a Starlette ASGI app for deployment.
"""

import logging
import sqlite3
from pathlib import Path
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
from ai_mailbox.tools.reply import tool_reply_to_message
from ai_mailbox.tools.thread import tool_get_thread
from ai_mailbox.tools.identity import tool_whoami
from ai_mailbox.tools.list_messages import tool_list_messages
from ai_mailbox.tools.mark_read import tool_mark_read
from ai_mailbox.tools.list_users import tool_list_users
from ai_mailbox.tools.create_group import tool_create_group
from ai_mailbox.tools.add_participant import tool_add_participant
from ai_mailbox.tools.search import tool_search_messages
from ai_mailbox.tools.acknowledge import tool_acknowledge
from ai_mailbox.tools.archive import tool_archive_conversation
from ai_mailbox.db.queries import update_last_seen
from ai_mailbox.web import create_web_routes
from ai_mailbox.web_oauth import create_oauth_routes

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
    """Upsert users with password hashes and seed invites."""
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

    # Seed invites from MAILBOX_INVITED_EMAILS
    if config.invited_emails:
        emails = [e.strip() for e in config.invited_emails.split(",") if e.strip()]
        for email in emails:
            existing = db.fetchone("SELECT email FROM user_invites WHERE email = ?", (email,))
            if not existing:
                db.execute(
                    "INSERT INTO user_invites (email, invited_by) VALUES (?, ?)",
                    (email, "keith"),
                )
        db.commit()
        logger.info(f"Seeded {len(emails)} invite(s)")


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

    # Validate configuration (fatal errors prevent startup)
    for warning in config.validate():
        logger.warning(warning)

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

    # Run initial token cleanup
    from ai_mailbox.token_cleanup import cleanup_expired_tokens
    cleanup_expired_tokens(db)

    # OAuth provider
    provider = MailboxOAuthProvider(db=db, jwt_secret=config.jwt_secret)
    _oauth_provider = provider

    # MCP server with OAuth — derive issuer URL from environment
    import os
    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
    if railway_domain:
        issuer_url = f"https://{railway_domain}"
    elif config.database_url:
        issuer_url = "https://ai-mailbox-server-production.up.railway.app"
    else:
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

    # --- MCP Apps: Inbox Widget Resource ---
    INBOX_WIDGET_URI = "ui://ai-mailbox/inbox.html"

    @mcp.resource(
        INBOX_WIDGET_URI,
        name="Inbox Widget",
        description="Interactive inbox for AI Mailbox",
        mime_type="text/html;profile=mcp-app",
    )
    def inbox_widget_resource() -> str:
        html_path = Path(__file__).parent / "ui" / "inbox_widget.html"
        return html_path.read_text(encoding="utf-8")

    # --- MCP Tools (user identity from OAuth token via contextvars) ---

    def _get_user() -> str:
        """Get authenticated user_id from OAuth context. Updates last_seen."""
        uid = current_user_id.get("unknown")
        logger.info(f"Tool call: authenticated as user={uid}")
        update_last_seen(db, uid)
        return uid

    @mcp.tool()
    def mailbox_send_message(
        body: str,
        to: str | list[str] | None = None,
        project: str = "general",
        subject: str = "",
        conversation_id: str | None = None,
        content_type: str = "text/plain",
        idempotency_key: str | None = None,
        group_name: str | None = None,
        group_send_token: str | None = None,
    ) -> dict:
        """Send a message via AI Mailbox. Use 'to' for direct (string) or group (list). Use 'conversation_id' for existing conversations. Group sends require a group_send_token from a confirmation step."""
        uid = _get_user()
        logger.info(f"send_message: from={uid} to={to} conv={conversation_id} project={project}")
        return tool_send_message(
            db, user_id=uid, to=to, body=body,
            project=project, subject=subject or None,
            conversation_id=conversation_id,
            content_type=content_type,
            idempotency_key=idempotency_key,
            group_name=group_name,
            group_send_token=group_send_token,
        )

    @mcp.tool(meta={"ui": {
        "resourceUri": INBOX_WIDGET_URI,
        "csp": {"resourceDomains": ["cdn.jsdelivr.net", "cdn.tailwindcss.com"]},
    }})
    def mailbox_list_messages(
        project: str = "",
        unread_only: bool = True,
        conversation_id: str | None = None,
        limit: int = 20,
        after_sequence: int = 0,
    ) -> dict:
        """List AI Mailbox messages without marking as read. Bodies truncated to 200 chars -- use mailbox_get_thread for full content. Pagination via after_sequence."""
        uid = _get_user()
        logger.info(f"list_messages: user={uid} project={project or 'all'} conv={conversation_id}")
        return tool_list_messages(
            db, user_id=uid,
            project=project or None, unread_only=unread_only,
            conversation_id=conversation_id,
            limit=limit, after_sequence=after_sequence,
        )

    @mcp.tool()
    def mailbox_mark_read(conversation_id: str, up_to_sequence: int | None = None) -> dict:
        """Mark AI Mailbox messages as read up to a sequence number in a conversation."""
        uid = _get_user()
        logger.info(f"mark_read: user={uid} conv={conversation_id} up_to={up_to_sequence}")
        return tool_mark_read(
            db, user_id=uid,
            conversation_id=conversation_id,
            up_to_sequence=up_to_sequence,
        )

    @mcp.tool()
    def mailbox_reply_to_message(
        message_id: str, body: str,
        content_type: str = "text/plain",
        idempotency_key: str | None = None,
    ) -> dict:
        """Reply to an AI Mailbox message. Inherits project and thread."""
        uid = _get_user()
        logger.info(f"reply_to_message: user={uid} message_id={message_id}")
        return tool_reply_to_message(
            db, user_id=uid, message_id=message_id, body=body,
            content_type=content_type,
            idempotency_key=idempotency_key,
        )

    @mcp.tool()
    def mailbox_get_thread(message_id: str, limit: int = 100, after_sequence: int = 0) -> dict:
        """Get the full AI Mailbox conversation thread from any message in it."""
        uid = _get_user()
        logger.info(f"get_thread: user={uid} message_id={message_id}")
        return tool_get_thread(
            db, user_id=uid, message_id=message_id,
            limit=limit, after_sequence=after_sequence,
        )

    @mcp.tool()
    def mailbox_whoami() -> dict:
        """AI Mailbox identity check. Returns your user info and unread counts per project."""
        uid = _get_user()
        logger.info(f"whoami: user={uid}")
        return tool_whoami(db, user_id=uid)

    @mcp.tool()
    def mailbox_list_users() -> dict:
        """List all registered AI Mailbox users (except yourself)."""
        uid = _get_user()
        logger.info(f"list_users: user={uid}")
        return tool_list_users(db, user_id=uid)

    @mcp.tool()
    def mailbox_create_group(name: str, members: list[str], project: str = "general") -> dict:
        """Create a named AI Mailbox group conversation."""
        uid = _get_user()
        logger.info(f"create_group: user={uid} name={name} members={members}")
        return tool_create_group(
            db, user_id=uid, name=name, members=members, project=project,
        )

    @mcp.tool()
    def mailbox_add_participant(conversation_id: str, user_to_add: str) -> dict:
        """Add a user to an AI Mailbox group conversation. Cannot add to direct conversations."""
        uid = _get_user()
        logger.info(f"add_participant: user={uid} conv={conversation_id} adding={user_to_add}")
        return tool_add_participant(
            db, user_id=uid,
            conversation_id=conversation_id,
            user_to_add=user_to_add,
        )

    @mcp.tool()
    def mailbox_search_messages(
        query: str,
        project: str | None = None,
        from_user: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Search AI Mailbox messages across all your conversations. Returns matching messages ordered by relevance."""
        uid = _get_user()
        logger.info(f"search_messages: user={uid} query={query!r}")
        return tool_search_messages(
            db, user_id=uid, query=query,
            project=project, from_user=from_user,
            since=since, until=until, limit=limit,
        )

    @mcp.tool()
    def mailbox_acknowledge(message_id: str, state: str) -> dict:
        """Acknowledge an AI Mailbox message. States: received, processing, completed, failed. Forward-only transitions."""
        uid = _get_user()
        logger.info(f"acknowledge: user={uid} message_id={message_id} state={state}")
        return tool_acknowledge(db, user_id=uid, message_id=message_id, state=state)

    @mcp.tool()
    def mailbox_archive_conversation(conversation_id: str, archive: bool = True) -> dict:
        """Archive or unarchive an AI Mailbox conversation. Archive=True to archive, False to unarchive."""
        uid = _get_user()
        logger.info(f"archive_conversation: user={uid} conv={conversation_id} archive={archive}")
        return tool_archive_conversation(
            db, user_id=uid, conversation_id=conversation_id, archive=archive,
        )

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
            "version": "0.6.0",
            "user_count": user_count,
            "auth": "oauth2.1",
        })

    # Web UI routes (Jinja2 + HTMX + Tailwind)
    web_routes = create_web_routes(
        db, provider, config.jwt_secret,
        github_oauth=config.github_oauth_available,
    )

    # OAuth routes (GitHub login)
    oauth_routes = []
    if config.github_oauth_available:
        oauth_routes = create_oauth_routes(db, provider, config, config.jwt_secret)

    mcp._custom_starlette_routes = [
        Route("/health", health),
        Route("/login", login_get, methods=["GET"]),
        Route("/login", login_post, methods=["POST"]),
    ] + oauth_routes + web_routes

    # Build ASGI app
    app = mcp.streamable_http_app()

    # CORS -- restricted to explicit origins
    from starlette.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.get_cors_origins(),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=True,
    )

    return app
