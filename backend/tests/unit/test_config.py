"""Unit tests for configuration validation and fail-fast startup."""

import pytest
from pydantic import ValidationError


def test_missing_required_env_var_raises_error_naming_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Config must refuse to start and clearly name missing required variables."""
    # Clear all settings from environment
    for var in [
        "DATABASE_URL",
        "REDIS_URL",
        "AUTH_JWKS_URL",
        "AUTH_ISSUER",
        "AUTH_AUDIENCE",
    ]:
        monkeypatch.delenv(var, raising=False)

    from app.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    errors = exc_info.value.errors()
    missing_fields = {err["loc"][0] for err in errors if err["type"] == "missing"}

    assert "database_url" in missing_fields or "DATABASE_URL" in missing_fields
    assert "redis_url" in missing_fields or "REDIS_URL" in missing_fields
    assert "auth_jwks_url" in missing_fields or "AUTH_JWKS_URL" in missing_fields
    assert "auth_issuer" in missing_fields or "AUTH_ISSUER" in missing_fields
    assert "auth_audience" in missing_fields or "AUTH_AUDIENCE" in missing_fields


def test_valid_config_loads_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid configuration correctly parses env vars and assigns sensible defaults."""
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/thinkloop"
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("AUTH_JWKS_URL", "https://auth.thinkloop.ai/.well-known/jwks.json")
    monkeypatch.setenv("AUTH_ISSUER", "https://auth.thinkloop.ai")
    monkeypatch.setenv("AUTH_AUDIENCE", "thinkloop-api")

    from app.config import Settings, get_settings

    settings = Settings()
    assert str(settings.database_url).startswith("postgresql+asyncpg://")
    assert str(settings.redis_url) == "redis://localhost:6379/0"
    assert str(settings.auth_jwks_url) == "https://auth.thinkloop.ai/.well-known/jwks.json"
    assert settings.auth_issuer == "https://auth.thinkloop.ai"
    assert settings.auth_audience == "thinkloop-api"
    assert settings.rate_limit_requests > 0
    assert settings.rate_limit_window_seconds > 0
    assert settings.jwks_cache_ttl_seconds > 0
    assert "Settings(" in repr(settings)
    assert get_settings() is not None


def test_empty_database_url_raises_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty string DATABASE_URL raises ValueError."""
    monkeypatch.setenv("DATABASE_URL", "   ")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("AUTH_JWKS_URL", "https://auth.thinkloop.ai/.well-known/jwks.json")
    monkeypatch.setenv("AUTH_ISSUER", "https://auth.thinkloop.ai")
    monkeypatch.setenv("AUTH_AUDIENCE", "thinkloop-api")

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings()
