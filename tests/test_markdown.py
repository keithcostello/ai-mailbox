"""Tests for the markdown rendering module."""

from markupsafe import Markup

from ai_mailbox.markdown import render_markdown


class TestBasicFormatting:
    def test_render_bold(self):
        result = render_markdown("**bold**")
        assert "<strong>bold</strong>" in result

    def test_render_italic(self):
        result = render_markdown("*italic*")
        assert "<em>italic</em>" in result

    def test_render_inline_code(self):
        result = render_markdown("`code`")
        assert "<code>code</code>" in result

    def test_render_code_block(self):
        result = render_markdown("```\nprint('hi')\n```")
        assert "<pre>" in result
        assert "<code>" in result

    def test_render_list(self):
        result = render_markdown("- item")
        assert "<ul>" in result
        assert "<li>" in result

    def test_render_heading(self):
        result = render_markdown("## Heading")
        assert "<h2>" in result
        assert "Heading" in result

    def test_render_link(self):
        result = render_markdown("[text](http://example.com)")
        assert '<a href="http://example.com">' in result
        assert "text</a>" in result


class TestPlugins:
    def test_render_strikethrough(self):
        result = render_markdown("~~deleted~~")
        assert "<del>deleted</del>" in result

    def test_render_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = render_markdown(md)
        assert "<table>" in result
        assert "<td>" in result


class TestXSSSafety:
    def test_xss_script_tag(self):
        result = render_markdown("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_xss_img_onerror(self):
        result = render_markdown('<img onerror="alert(1)">')
        assert "<img" not in result
        assert "&lt;img" in result


class TestEdgeCases:
    def test_plain_text_passthrough(self):
        result = render_markdown("Hello world")
        assert "Hello world" in result
        assert "<p>" in result

    def test_empty_string(self):
        result = render_markdown("")
        assert result == ""
        assert isinstance(result, Markup)

    def test_multiline(self):
        result = render_markdown("First paragraph\n\nSecond paragraph")
        assert "First paragraph" in result
        assert "Second paragraph" in result
        # Two separate <p> tags
        assert result.count("<p>") == 2

    def test_returns_markup_type(self):
        result = render_markdown("hello")
        assert isinstance(result, Markup)
