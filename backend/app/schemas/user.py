"""User schemas for client data exchange."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserRead(BaseModel):
    """Public read representation of a User."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique user identifier")
    email: str | None = Field(None, description="User email address")
    created_at: datetime = Field(..., description="Timestamp of user account creation")
