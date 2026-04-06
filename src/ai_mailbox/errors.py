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
    # Sprint 2
    "RATE_LIMITED":           {"retryable": True},
    "BODY_TOO_LONG":          {"retryable": False},
    "GROUP_TOO_LARGE":        {"retryable": False},
    "INVALID_PARAMETER":      {"retryable": False},
    "MISSING_PARAMETER":      {"retryable": False},
    "GROUP_CONFIRMATION_REQUIRED": {"retryable": False},
    "GROUP_TOKEN_EXPIRED":    {"retryable": False},
    "GROUP_TOKEN_INVALID":    {"retryable": False},
    # Sprint 4
    "INVALID_JSON":           {"retryable": False},
    # Sprint 5
    "INVALID_STATE_TRANSITION": {"retryable": False},
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
