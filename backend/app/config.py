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
    embedding_dim: int = Field(default=1024, description="Vector embedding dimension")
    embedding_endpoint_url: str | None = Field(
        default=None, description="URL for HTTP embeddings provider"
    )
    embedding_api_key: str | None = Field(
        default=None, description="API key for HTTP embeddings provider"
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Model name for HTTP embeddings provider",
    )

    # LLM Settings
    anthropic_api_key: str | None = Field(
        default=None,
        description="Anthropic API key for tutor dialogue and diagnosis",
    )
    fast_model: str = Field(
        default="claude-3-5-haiku-latest",
        description="Fast model for diagnosis and classification",
    )
    strong_model: str = Field(
        default="claude-3-5-sonnet-latest",
        description="Strong model for tutor replies",
    )
    gemini_api_key: str | None = Field(
        default=None,
        description="Google Gemini API key for embeddings and Socratic dialogue",
    )

    # Strategy & Pedagogical Thresholds
    strategy_mastery_low_threshold: float = Field(
        default=0.35,
        description="Mastery threshold below which worked_example is chosen",
    )
    strategy_mastery_high_threshold: float = Field(
        default=0.70,
        description="Mastery threshold above which socratic_challenge is chosen",
    )
    diagnoser_confidence_threshold: float = Field(
        default=0.70,
        description="Confidence threshold for misconception detection and grading",
    )
    prerequisite_weak_threshold: float = Field(
        default=0.40,
        description="Mastery threshold below which a prerequisite is considered weak",
    )

    # Feature Flags (Phases 9-16)
    feature_battle: bool = Field(default=True, description="Enable Battle with AI")
    feature_focus: bool = Field(default=True, description="Enable Focus Timer")
    feature_flashcards: bool = Field(default=True, description="Enable Spaced Flashcards")
    feature_doubts: bool = Field(default=True, description="Enable Doubt Log")
    feature_streak: bool = Field(default=True, description="Enable Streak Calendar")
    feature_voice: bool = Field(default=True, description="Enable Voice Mode")
    feature_videos: bool = Field(default=True, description="Enable YouTube Video Suggestions")

    # Streak & Calendar Rules (Phase 10)
    streak_freeze_earn_days: int = Field(
        default=7, description="Number of consecutive active days needed to earn 1 freeze"
    )
    streak_freeze_max_cap: int = Field(
        default=2, description="Maximum number of banked streak freezes"
    )
    streak_initial_freezes: int = Field(
        default=1, description="Initial free freezes for new user streak state"
    )
    streak_min_focus_minutes: int = Field(
        default=10, description="Minimum focus minutes for a qualifying day"
    )
    streak_min_tutor_turns: int = Field(
        default=1, description="Minimum gradable tutor turns for a qualifying day"
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
