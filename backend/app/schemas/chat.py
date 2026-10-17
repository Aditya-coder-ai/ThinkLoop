"""Pydantic schemas for dialogue sessions and chat streaming."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    """Payload to start a dialogue session for a concept."""

    model_config = ConfigDict(extra="forbid")
    concept_id: str = Field(..., description="ID of the concept to tutor")


class TurnRead(BaseModel):
    """Representation of an individual dialogue turn."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    diagnosis: dict[str, Any] | None = None
    strategy: str | None = None
    prompt_versions: dict[str, Any] | None = None
    token_usage: dict[str, Any] | None = None
    leak_suspected: bool = False
    created_at: datetime


class SessionRead(BaseModel):
    """Full dialogue session representation including turns."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    concept_id: str
    summary: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    turns: list[TurnRead] = Field(default_factory=list)


class MessageRequest(BaseModel):
    """Learner chat message payload."""

    model_config = ConfigDict(extra="forbid")
    content: str = Field(..., min_length=1, max_length=10000, description="Learner message text")
