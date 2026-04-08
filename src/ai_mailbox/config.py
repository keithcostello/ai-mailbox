"""AI Mailbox configuration — loaded from environment variables."""

import os
from dataclasses import dataclass, field
from typing import List

MAX_BODY_LENGTH = 10_000
MAX_GROUP_SIZE = 50
THREAD_BODY_DISPLAY_LIMIT = 2_000
THREAD_DEFAULT_LIMIT = 5
DEAD_LETTER_THRESHOLD_HOURS = 24
MAX_PROFILE_METADATA_SIZE = 10_000
MAX_EXPERTISE_TAGS = 50
MAX_FIND_EXPERTS_TAGS = 20
BROADCAST_DEFAULT_EXPIRY_HOURS = 48
BROADCAST_COOLDOWN_HOURS = 24
BROADCAST_MAX_TAGS = 10

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
    github_client_id: str = ""
    github_client_secret: str = ""
    invite_only: bool = True
    invited_emails: str = ""

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

    @property
    def github_oauth_available(self) -> bool:
        """True when GitHub OAuth client credentials are configured."""
        return bool(self.github_client_id and self.github_client_secret)

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
            github_client_id=os.environ.get("GITHUB_CLIENT_ID", ""),
            github_client_secret=os.environ.get("GITHUB_CLIENT_SECRET", ""),
            invite_only=os.environ.get("MAILBOX_INVITE_ONLY", "true").lower() in ("true", "1", "yes"),
            invited_emails=os.environ.get("MAILBOX_INVITED_EMAILS", ""),
        )
