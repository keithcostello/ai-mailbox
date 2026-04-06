"""Server integration tests -- app creation, health, tools, web routes."""

import os
import pytest
from httpx import ASGITransport, AsyncClient

# Set required env vars before importing server
os.environ.setdefault("MAILBOX_JWT_SECRET", "test-jwt-secret-minimum-32-bytes-long!")
os.environ.setdefault("MAILBOX_KEITH_PASSWORD", "keith123")
os.environ.setdefault("MAILBOX_AMY_PASSWORD", "amy123")
os.environ.setdefault("DATABASE_URL", "")  # Empty = SQLite mode


@pytest.mark.asyncio
async def test_create_app_returns_starlette_app():
    """create_app() doesn't crash, returns ASGI app."""
    from ai_mailbox.server import create_app
    app = create_app()
    assert app is not None
    assert callable(app)


@pytest.mark.asyncio
async def test_health_endpoint_returns_200():
    """/health responds with status=healthy."""
    from ai_mailbox.server import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["auth"] == "oauth2.1"


@pytest.mark.asyncio
async def test_health_shows_user_count():
    """/health includes registered user count."""
    from ai_mailbox.server import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    data = resp.json()
    assert data["user_count"] == 2


@pytest.mark.asyncio
async def test_mcp_tools_registered():
    """All 5 tools are registered on the MCP server."""
    from ai_mailbox.server import create_app, _mcp_instance
    create_app()
    assert _mcp_instance is not None
    tools = await _mcp_instance.list_tools()
    tool_names = {t.name for t in tools}
    expected = {
        "send_message", "reply_to_message", "get_thread", "whoami",
        # Sprint 2
        "list_messages", "mark_read", "list_users", "create_group", "add_participant",
        # Sprint 4
        "search_messages",
    }
    assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"


@pytest.mark.asyncio
async def test_login_page_renders():
    """/login returns HTML login form (OAuth login, not web login)."""
    from ai_mailbox.server import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/login?client_id=test&code_challenge=abc&redirect_uri=http://localhost&state=xyz&scopes=read")
    assert resp.status_code == 200
    assert "username" in resp.text


@pytest.mark.asyncio
async def test_web_login_page_renders():
    """/web/login returns styled web login form."""
    from ai_mailbox.server import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/web/login")
    assert resp.status_code == 200
    assert "daisyui" in resp.text.lower()
    assert "htmx.org" in resp.text
    assert "fantasy" in resp.text.lower()  # DaisyUI theme


@pytest.mark.asyncio
async def test_web_health_page_renders():
    """/web/health returns health dashboard."""
    from ai_mailbox.server import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/web/health")
    assert resp.status_code == 200
    assert "HEALTHY" in resp.text


@pytest.mark.asyncio
async def test_web_inbox_requires_auth():
    """/web/inbox redirects to login without session."""
    from ai_mailbox.server import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        resp = await client.get("/web/inbox")
    assert resp.status_code == 302
    assert "/web/login" in resp.headers["location"]
