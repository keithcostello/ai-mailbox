"""AI Mailbox configuration — loaded from environment variables."""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """Server configuration."""

    database_url: str = ""
    port: int = 8000
    jwt_secret: str = "change-me-in-production-minimum-32-bytes!"
    keith_password: str = ""
    amy_password: str = ""
    # Legacy API key support (kept for backward compatibility)
    keith_api_key: str = ""
    amy_api_key: str = ""
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            database_url=os.environ.get("DATABASE_URL", ""),
            port=int(os.environ.get("PORT", "8000")),
            jwt_secret=os.environ.get("MAILBOX_JWT_SECRET", "change-me-in-production-minimum-32-bytes!"),
            keith_password=os.environ.get("MAILBOX_KEITH_PASSWORD", ""),
            amy_password=os.environ.get("MAILBOX_AMY_PASSWORD", ""),
            keith_api_key=os.environ.get("MAILBOX_KEITH_API_KEY", ""),
            amy_api_key=os.environ.get("MAILBOX_AMY_API_KEY", ""),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
