"""Tests for MCP Apps inbox widget — resource registration and HTML content."""

from pathlib import Path

import pytest


_UI_DIR = Path(__file__).parent.parent / "src" / "ai_mailbox" / "ui"
_WIDGET_PATH = _UI_DIR / "inbox_widget.html"


def _read_widget_html() -> str:
    return _WIDGET_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Widget HTML file existence and structure
# ---------------------------------------------------------------------------

class TestWidgetHtmlFile:
    """inbox_widget.html exists and has required structure."""

    def test_file_exists(self):
        assert _WIDGET_PATH.exists(), f"Widget HTML not found at {_WIDGET_PATH}"

    def test_is_valid_html(self):
        html = _read_widget_html()
        assert "<!DOCTYPE html>" in html or "<!doctype html>" in html

    def test_has_app_connect(self):
        """Widget must call app.connect() for MCP Apps handshake."""
        html = _read_widget_html()
        assert "connect()" in html

    def test_has_callservertool(self):
        """Widget must use callServerTool to communicate with server."""
        html = _read_widget_html()
        assert "callServerTool" in html

    def test_has_ontoolresult(self):
        """Widget must handle initial tool result from host."""
        html = _read_widget_html()
        assert "ontoolresult" in html

    def test_references_daisyui(self):
        """Widget uses DaisyUI for consistent styling with web UI."""
        html = _read_widget_html()
        assert "daisyui" in html.lower()

    def test_has_ext_apps_import(self):
        """Widget imports the MCP Apps client SDK."""
        html = _read_widget_html()
        assert "ext-apps" in html or "modelcontextprotocol" in html

    def test_has_inbox_view(self):
        """Widget has conversation list / inbox rendering."""
        html = _read_widget_html()
        assert "inbox" in html.lower()

    def test_has_thread_view(self):
        """Widget has thread / message detail rendering."""
        html = _read_widget_html()
        assert "thread" in html.lower()

    def test_has_compose_view(self):
        """Widget has compose / new message functionality."""
        html = _read_widget_html()
        assert "compose" in html.lower()

    def test_has_reply_functionality(self):
        """Widget supports replying to messages."""
        html = _read_widget_html()
        assert "reply" in html.lower()

    def test_has_polling(self):
        """Widget polls for new messages."""
        html = _read_widget_html()
        assert "setInterval" in html or "setTimeout" in html

    def test_has_relative_time(self):
        """Widget formats timestamps as relative time."""
        html = _read_widget_html()
        assert "relativeTime" in html or "relative_time" in html or "timeAgo" in html


# ---------------------------------------------------------------------------
# Server-side resource registration
# ---------------------------------------------------------------------------

class TestMcpAppsServerIntegration:
    """MCP server registers inbox widget resource and tool metadata."""

    def test_ui_directory_exists(self):
        assert _UI_DIR.exists(), f"ui/ directory not found at {_UI_DIR}"

    def test_ui_init_exists(self):
        init = _UI_DIR / "__init__.py"
        assert init.exists(), "ui/__init__.py required for package"
