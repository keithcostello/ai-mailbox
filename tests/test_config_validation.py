"""Sprint 3 Step 1+3: Config validation and cleanup tests."""

import pytest

from ai_mailbox.config import Config, ConfigurationError

_VALID_SECRET = "a-valid-secret-that-is-at-least-32-bytes-long!"
_DEFAULT_SECRET = "change-me-in-production-minimum-32-bytes!"


# --- validate() ---


def test_validate_default_secret_with_postgres_raises():
    """Default secret + PostgreSQL database_url must raise ConfigurationError."""
    cfg = Config(database_url="postgresql://localhost/mailbox", jwt_secret=_DEFAULT_SECRET)
    with pytest.raises(ConfigurationError):
        cfg.validate()


def test_validate_default_secret_sqlite_warns():
    """Default secret + no database_url (SQLite) returns a warning list."""
    cfg = Config(database_url="", jwt_secret=_DEFAULT_SECRET)
    warnings = cfg.validate()
    assert len(warnings) > 0
    assert any("secret" in w.lower() for w in warnings)


def test_validate_short_secret_raises():
    """Secret shorter than 32 bytes must raise ConfigurationError regardless of DB."""
    cfg = Config(jwt_secret="too-short")
    with pytest.raises(ConfigurationError):
        cfg.validate()


def test_validate_valid_secret_no_warnings():
    """Valid 32+ byte secret returns empty warning list."""
    cfg = Config(jwt_secret=_VALID_SECRET)
    warnings = cfg.validate()
    assert warnings == []


def test_validate_empty_secret_raises():
    """Empty string secret must raise ConfigurationError."""
    cfg = Config(jwt_secret="")
    with pytest.raises(ConfigurationError):
        cfg.validate()


# --- get_cors_origins() ---


def test_cors_origins_default():
    """No allowed_origins -> Railway URL + localhost only."""
    cfg = Config(allowed_origins="")
    origins = cfg.get_cors_origins()
    assert "https://ai-mailbox-server-mvp-1-staging.up.railway.app" in origins
    assert "http://localhost:8000" in origins
    assert len(origins) == 2


def test_cors_origins_custom():
    """Custom origins are added alongside the defaults."""
    cfg = Config(allowed_origins="https://example.com,https://other.dev")
    origins = cfg.get_cors_origins()
    assert "https://example.com" in origins
    assert "https://other.dev" in origins
    assert "https://ai-mailbox-server-mvp-1-staging.up.railway.app" in origins
    assert "http://localhost:8000" in origins
    assert len(origins) == 4


def test_cors_origins_deduplication():
    """Duplicate origins are removed."""
    cfg = Config(allowed_origins="http://localhost:8000,https://example.com,http://localhost:8000")
    origins = cfg.get_cors_origins()
    assert origins.count("http://localhost:8000") == 1
    assert len(origins) == 3  # 2 defaults + 1 custom (example.com)


# --- Legacy field removal ---


def test_api_key_fields_removed():
    """Config should NOT have keith_api_key or amy_api_key attributes."""
    cfg = Config()
    assert not hasattr(cfg, "keith_api_key")
    assert not hasattr(cfg, "amy_api_key")


# --- auth.py deletion ---


def test_auth_module_deleted():
    """Importing ai_mailbox.auth should raise ImportError."""
    with pytest.raises(ImportError):
        import ai_mailbox.auth  # noqa: F401
