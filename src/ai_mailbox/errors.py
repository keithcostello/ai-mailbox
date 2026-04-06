"""Structured error framework for AI Mailbox MCP tools."""

ERROR_CODES: dict[str, dict] = {
    "VALIDATION_ERROR":       {"retryable": False},
    "EMPTY_BODY":             {"retryable": False},
    "SELF_SEND":              {"retryable": False},
    "RECIPIENT_NOT_FOUND":    {"retryable": False},
    "MESSAGE_NOT_FOUND":      {"retryable": False},
    "CONVERSATION_NOT_FOUND": {"retryable": False},
    "PERMISSION_DENIED":      {"retryable": False},
    "DUPLICATE_MESSAGE":      {"retryable": False},
    "SEQUENCE_CONFLICT":      {"retryable": True},
    "INTERNAL_ERROR":         {"retryable": True},
}


def make_error(code: str, message: str, param: str | None = None) -> dict:
    """Create structured error response."""
    retryable = ERROR_CODES.get(code, {}).get("retryable", False)
    error = {"code": code, "message": message, "retryable": retryable}
    if param is not None:
        error["param"] = param
    return {"error": error}


def is_error(result: dict) -> bool:
    """Check if a tool result is a structured error."""
    return "error" in result and isinstance(result["error"], dict)
