"""Application configuration management with strict environment validation."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Thinkloop runtime settings populated from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Required settings (fail-fast at startup if missing)
    database_url: str = Field(
        ...,
        description="Async PostgreSQL connection URI (e.g. postgresql+asyncpg://...)",
    )
    redis_url: str = Field(
        ...,
        description="Redis connection URI (e.g. redis://localhost:6379/0)",
    )
    auth_jwks_url: str = Field(
        ...,
        description="Public JWKS JSON endpoint for JWT verification",
    )
    auth_issuer: str = Field(
        ...,
        description="Expected JWT issuer claim ('iss')",
    )
    auth_audience: str = Field(
        ...,
        description="Expected JWT audience claim ('aud')",
    )

    # Optional configuration overrides
    environment: Literal["development", "staging", "production", "test"] = "development"
    log_level: str = "INFO"
    jwks_cache_ttl_seconds: int = 3600
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # Optional AI/LLM extension point (Part 2/3)
    gemini_api_key: str | None = Field(
        default=None,
        description="Google Gemini API key for embeddings and Socratic dialogue",
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url_scheme(cls, v: str) -> str:
        """Ensure database URL is non-empty and formatted."""
        if not v or not v.strip():
            raise ValueError("DATABASE_URL must not be empty")
        return v.strip()

    def __repr__(self) -> str:
        """Safe string representation that never exposes connection secrets."""
        return (
            f"Settings(environment={self.environment!r}, "
            f"auth_issuer={self.auth_issuer!r}, "
            f"auth_audience={self.auth_audience!r})"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
