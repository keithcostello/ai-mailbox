"""Markdown rendering for message bodies -- safe HTML output via mistune."""

import mistune
from markupsafe import Markup

_renderer = mistune.create_markdown(
    escape=True,  # CRITICAL: escape HTML in input to prevent XSS
    plugins=['strikethrough', 'table'],
)


def render_markdown(text: str) -> Markup:
    """Render markdown text to safe HTML. Returns Markup for Jinja2 autoescape."""
    if not text:
        return Markup("")
    result = _renderer(text)
    return Markup(result)
