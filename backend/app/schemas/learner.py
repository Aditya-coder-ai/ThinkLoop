"""Pydantic schemas for Learner Profile and Mastery progress."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProfileRead(BaseModel):
    """Public read representation of a learner profile."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str = Field(..., description="Authenticated user identifier")
    display_name: str | None = Field(None, description="Learner display name")
    learning_level: str | None = Field(None, description="Self-identified learning level")
    exam_target: str | None = Field(None, description="Target exam or learning goal")
    created_at: datetime = Field(..., description="Profile creation timestamp")
    updated_at: datetime = Field(..., description="Profile last updated timestamp")


class ProfileUpdate(BaseModel):
    """Request payload to create or update a learner profile."""

    display_name: str | None = Field(None, description="Learner display name", max_length=100)
    learning_level: str | None = Field(None, description="Self-identified learning level", max_length=50)
    exam_target: str | None = Field(None, description="Target exam or learning goal", max_length=100)


class LearnerMasteryRead(BaseModel):
    """Read representation of concept mastery for a learner."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Mastery record identifier")
    user_id: str = Field(..., description="Authenticated user identifier")
    concept_id: str = Field(..., description="Concept identifier")
    mastery_score: float = Field(..., ge=0.0, le=1.0, description="Mastery score from 0.0 to 1.0")
    attempts: int = Field(..., ge=0, description="Cumulative practice attempts count")
    last_practiced_at: datetime | None = Field(None, description="Timestamp of last practice session")
    next_review_at: datetime | None = Field(None, description="Calculated next spaced-repetition review")
    updated_at: datetime = Field(..., description="Timestamp of last mastery update")


class LearnerMasteryUpsert(BaseModel):
    """Request payload to record or update mastery progress."""

    concept_id: str = Field(..., description="Target concept identifier")
    mastery_score: float = Field(..., ge=0.0, le=1.0, description="Mastery score between 0.0 and 1.0")
    attempts_increment: int = Field(1, ge=1, description="Number of attempts to increment")
    last_practiced_at: datetime | None = Field(None, description="Timestamp of practice session")
    next_review_at: datetime | None = Field(None, description="Scheduled next review date")
