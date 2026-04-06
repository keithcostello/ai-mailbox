"""Tests for the structured error framework."""
import pytest

from ai_mailbox.errors import make_error, is_error, ERROR_CODES


class TestMakeError:
    """make_error produces the correct structure."""

    def test_basic_error(self):
        result = make_error("RECIPIENT_NOT_FOUND", "User 'bob' does not exist")
        assert result == {
            "error": {
                "code": "RECIPIENT_NOT_FOUND",
                "message": "User 'bob' does not exist",
                "retryable": False,
            }
        }

    def test_error_with_param(self):
        result = make_error("EMPTY_BODY", "Message body cannot be empty", param="body")
        assert result["error"]["param"] == "body"
        assert result["error"]["code"] == "EMPTY_BODY"

    def test_retryable_error(self):
        result = make_error("SEQUENCE_CONFLICT", "concurrent insert, retry exhausted")
        assert result["error"]["retryable"] is True

    def test_internal_error_is_retryable(self):
        result = make_error("INTERNAL_ERROR", "unexpected failure")
        assert result["error"]["retryable"] is True

    def test_non_retryable_errors(self):
        non_retryable = [
            "VALIDATION_ERROR", "EMPTY_BODY", "SELF_SEND",
            "RECIPIENT_NOT_FOUND", "MESSAGE_NOT_FOUND",
            "CONVERSATION_NOT_FOUND", "PERMISSION_DENIED",
            "DUPLICATE_MESSAGE",
        ]
        for code in non_retryable:
            result = make_error(code, "test")
            assert result["error"]["retryable"] is False, f"{code} should not be retryable"

    def test_param_omitted_when_none(self):
        result = make_error("INTERNAL_ERROR", "boom")
        assert "param" not in result["error"]

    def test_param_included_when_provided(self):
        result = make_error("VALIDATION_ERROR", "missing field", param="to")
        assert result["error"]["param"] == "to"

    def test_unknown_code_defaults_non_retryable(self):
        result = make_error("UNKNOWN_CODE", "something weird")
        assert result["error"]["retryable"] is False
        assert result["error"]["code"] == "UNKNOWN_CODE"


class TestIsError:
    """is_error correctly identifies error vs success responses."""

    def test_structured_error(self):
        result = make_error("SELF_SEND", "cannot send to self")
        assert is_error(result) is True

    def test_success_dict(self):
        result = {"message_id": "abc", "from_user": "keith"}
        assert is_error(result) is False

    def test_empty_dict(self):
        assert is_error({}) is False

    def test_old_style_string_error_not_matched(self):
        """Old-style {error: 'string'} is NOT a structured error."""
        result = {"error": "some string"}
        assert is_error(result) is False


class TestErrorCodeRegistry:
    """ERROR_CODES registry is complete."""

    def test_all_codes_defined(self):
        expected = {
            "VALIDATION_ERROR", "EMPTY_BODY", "SELF_SEND",
            "RECIPIENT_NOT_FOUND", "MESSAGE_NOT_FOUND",
            "CONVERSATION_NOT_FOUND", "PERMISSION_DENIED",
            "DUPLICATE_MESSAGE", "SEQUENCE_CONFLICT", "INTERNAL_ERROR",
        }
        assert set(ERROR_CODES.keys()) == expected

    def test_each_code_has_retryable_field(self):
        for code, meta in ERROR_CODES.items():
            assert "retryable" in meta, f"{code} missing 'retryable'"
            assert isinstance(meta["retryable"], bool), f"{code} retryable must be bool"
