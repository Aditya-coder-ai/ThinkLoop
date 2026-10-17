"""Schemas for learner activity events."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ActivityKind = Literal[
    "tutor_turn_gradable",
    "review_completed",
    "focus_completed",
    "battle_completed",
    "flashcard_reviewed",
    "doubt_resolved",
    "voice_session",
]


class ActivityEventRead(BaseModel):
    """Schema for reading an activity event."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    kind: str
    ref_type: str | None = None
    ref_id: str
    occurred_at: datetime
    local_date: date
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
