"""Schemas for user preferences with IANA timezone validation."""

import uuid
import zoneinfo
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def validate_iana_timezone(v: str) -> str:
    """Validate that a string corresponds to a valid IANA timezone."""
    try:
        zoneinfo.ZoneInfo(v)
    except Exception as err:
        raise ValueError(f"Invalid IANA timezone: '{v}'") from err
    return v


class UserPreferencesRead(BaseModel):
    """Schema for reading user preferences."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    timezone: str
    daily_goal_minutes: int
    voice_enabled: bool
    preferred_voice: str
    locale: str
    created_at: datetime
    updated_at: datetime


class UserPreferencesUpdate(BaseModel):
    """Schema for updating user preferences."""

    timezone: str | None = Field(default=None, description="Valid IANA timezone identifier")
    daily_goal_minutes: int | None = Field(default=None, ge=1, le=1440)
    voice_enabled: bool | None = None
    preferred_voice: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=32)

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, v: str | None) -> str | None:
        if v is not None:
            return validate_iana_timezone(v)
        return v
