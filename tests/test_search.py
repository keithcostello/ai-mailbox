"""Tests for search_messages query + tool (SQLite LIKE path)."""
import pytest
from ai_mailbox.tools.send import tool_send_message
from ai_mailbox.tools.search import tool_search_messages
from ai_mailbox.db.queries import search_messages
from ai_mailbox.errors import is_error


class TestSearchMessages:
    def test_search_finds_matching_body(self, db):
        tool_send_message(db, user_id="keith", to="amy", body="Deploy the railway app")
        results = search_messages(db, "amy", "railway")
        assert len(results) == 1
        assert "railway" in results[0]["body"].lower()

    def test_search_finds_matching_subject(self, db):
        tool_send_message(db, user_id="keith", to="amy", body="See subject", subject="Railway deploy")
        results = search_messages(db, "amy", "Railway")
        assert len(results) == 1

    def test_search_respects_participant_filter(self, db):
        """User can only search their own conversations."""
        tool_send_message(db, user_id="keith", to="amy", body="Secret railway info")
        # bob is not in this conversation
        db._conn.execute("INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)", ("bob", "Bob", "k3"))
        db._conn.commit()
        results = search_messages(db, "bob", "railway")
        assert len(results) == 0

    def test_search_project_filter(self, db):
        tool_send_message(db, user_id="keith", to="amy", body="Railway deploy", project="steertrue")
        tool_send_message(db, user_id="keith", to="amy", body="Railway config", project="general")
        results = search_messages(db, "amy", "Railway", project="steertrue")
        assert len(results) == 1
        assert results[0]["project"] == "steertrue"

    def test_search_from_user_filter(self, db):
        tool_send_message(db, user_id="keith", to="amy", body="Railway from keith")
        tool_send_message(db, user_id="amy", to="keith", body="Railway from amy")
        results = search_messages(db, "keith", "Railway", from_user="amy")
        assert len(results) == 1
        assert results[0]["from_user"] == "amy"

    def test_search_since_filter(self, db):
        tool_send_message(db, user_id="keith", to="amy", body="Railway old")
        results = search_messages(db, "amy", "Railway", since="2099-01-01T00:00:00Z")
        assert len(results) == 0

    def test_search_until_filter(self, db):
        tool_send_message(db, user_id="keith", to="amy", body="Railway new")
        results = search_messages(db, "amy", "Railway", until="2000-01-01T00:00:00Z")
        assert len(results) == 0

    def test_search_limit(self, db):
        for i in range(5):
            tool_send_message(db, user_id="keith", to="amy", body=f"Railway msg {i}", project=f"p{i}")
        results = search_messages(db, "amy", "Railway", limit=3)
        assert len(results) == 3

    def test_search_empty_results(self, db):
        results = search_messages(db, "amy", "nonexistent")
        assert results == []

    def test_search_case_insensitive(self, db):
        tool_send_message(db, user_id="keith", to="amy", body="RAILWAY deploy")
        results = search_messages(db, "amy", "railway")
        assert len(results) == 1

    def test_search_includes_project_field(self, db):
        tool_send_message(db, user_id="keith", to="amy", body="Railway test", project="steertrue")
        results = search_messages(db, "amy", "Railway")
        assert results[0]["project"] == "steertrue"


class TestSearchTool:
    """Tests for the search_messages MCP tool wrapper."""

    def test_tool_returns_structured_response(self, db):
        tool_send_message(db, user_id="keith", to="amy", body="Deploy railway")
        result = tool_search_messages(db, user_id="amy", query="railway")
        assert result["query"] == "railway"
        assert result["result_count"] == 1
        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert "id" in msg
        assert "conversation_id" in msg
        assert "body_preview" in msg

    def test_tool_empty_query_error(self, db):
        result = tool_search_messages(db, user_id="amy", query="")
        assert is_error(result)
        assert result["error"]["code"] == "MISSING_PARAMETER"

    def test_tool_whitespace_query_error(self, db):
        result = tool_search_messages(db, user_id="amy", query="   ")
        assert is_error(result)
        assert result["error"]["code"] == "MISSING_PARAMETER"

    def test_tool_query_too_long(self, db):
        result = tool_search_messages(db, user_id="amy", query="x" * 501)
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_PARAMETER"
        assert result["error"]["param"] == "query"

    def test_tool_limit_out_of_range(self, db):
        result = tool_search_messages(db, user_id="amy", query="test", limit=0)
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_PARAMETER"
        assert result["error"]["param"] == "limit"

    def test_tool_limit_over_max(self, db):
        result = tool_search_messages(db, user_id="amy", query="test", limit=101)
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_PARAMETER"

    def test_tool_invalid_since(self, db):
        result = tool_search_messages(db, user_id="amy", query="test", since="not-a-date")
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_PARAMETER"
        assert result["error"]["param"] == "since"

    def test_tool_invalid_until(self, db):
        result = tool_search_messages(db, user_id="amy", query="test", until="nope")
        assert is_error(result)
        assert result["error"]["code"] == "INVALID_PARAMETER"

    def test_tool_body_preview_truncation(self, db):
        long_body = "railway " + "x" * 300
        tool_send_message(db, user_id="keith", to="amy", body=long_body)
        result = tool_search_messages(db, user_id="amy", query="railway")
        msg = result["messages"][0]
        assert len(msg["body_preview"]) <= 203  # 200 + "..."
        assert msg["body_preview"].endswith("...")

    def test_tool_project_filter(self, db):
        tool_send_message(db, user_id="keith", to="amy", body="Railway a", project="proj1")
        tool_send_message(db, user_id="keith", to="amy", body="Railway b", project="proj2")
        result = tool_search_messages(db, user_id="amy", query="Railway", project="proj1")
        assert result["result_count"] == 1

    def test_tool_from_user_filter(self, db):
        tool_send_message(db, user_id="keith", to="amy", body="Railway k")
        tool_send_message(db, user_id="amy", to="keith", body="Railway a")
        result = tool_search_messages(db, user_id="keith", query="Railway", from_user="amy")
        assert result["result_count"] == 1
        assert result["messages"][0]["from_user"] == "amy"

    def test_tool_no_results(self, db):
        result = tool_search_messages(db, user_id="amy", query="nonexistent")
        assert result["result_count"] == 0
        assert result["messages"] == []

    def test_tool_valid_since_until(self, db):
        tool_send_message(db, user_id="keith", to="amy", body="Railway msg")
        result = tool_search_messages(
            db, user_id="amy", query="Railway",
            since="2020-01-01T00:00:00Z", until="2099-12-31T23:59:59Z",
        )
        assert result["result_count"] == 1
