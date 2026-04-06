"""AI Mailbox configuration — loaded from environment variables."""

import os
from dataclasses import dataclass, field
from typing import List

MAX_BODY_LENGTH = 10_000
MAX_GROUP_SIZE = 50

_DEFAULT_SECRET = "change-me-in-production-minimum-32-bytes!"

_RAILWAY_ORIGIN = "https://ai-mailbox-server-mvp-1-staging.up.railway.app"
_LOCALHOST_ORIGIN = "http://localhost:8000"


class ConfigurationError(Exception):
    """Raised when configuration is invalid and the server cannot start safely."""


@dataclass
class Config:
    """Server configuration."""

    database_url: str = ""
    port: int = 8000
    jwt_secret: str = _DEFAULT_SECRET
    keith_password: str = ""
    amy_password: str = ""
    allowed_origins: str = ""
    log_level: str = "INFO"

    def validate(self) -> List[str]:
        """Validate configuration. Returns warnings list or raises ConfigurationError."""
        warnings: List[str] = []

        if not self.jwt_secret or len(self.jwt_secret) < 32:
            raise ConfigurationError(
                f"jwt_secret must be at least 32 bytes (got {len(self.jwt_secret)})"
            )

        if self.jwt_secret == _DEFAULT_SECRET:
            if self.database_url and self.database_url.startswith("postgres"):
                raise ConfigurationError(
                    "Default jwt_secret cannot be used with a PostgreSQL database. "
                    "Set MAILBOX_JWT_SECRET to a unique value."
                )
            warnings.append(
                "Using default jwt_secret — acceptable for local SQLite development only."
            )

        return warnings

    def get_cors_origins(self) -> List[str]:
        """Parse allowed_origins and merge with built-in defaults."""
        origins: List[str] = [_RAILWAY_ORIGIN, _LOCALHOST_ORIGIN]

        if self.allowed_origins:
            for origin in self.allowed_origins.split(","):
                origin = origin.strip()
                if origin:
                    origins.append(origin)

        # Deduplicate while preserving order
        seen: set = set()
        unique: List[str] = []
        for o in origins:
            if o not in seen:
                seen.add(o)
                unique.append(o)
        return unique

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            database_url=os.environ.get("DATABASE_URL", ""),
            port=int(os.environ.get("PORT", "8000")),
            jwt_secret=os.environ.get("MAILBOX_JWT_SECRET", _DEFAULT_SECRET),
            keith_password=os.environ.get("MAILBOX_KEITH_PASSWORD", ""),
            amy_password=os.environ.get("MAILBOX_AMY_PASSWORD", ""),
            allowed_origins=os.environ.get("MAILBOX_CORS_ORIGINS", ""),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
