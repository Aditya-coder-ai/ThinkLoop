"""Pydantic schemas for learner message diagnosis and classification."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Understanding = Literal["correct", "partial", "incorrect", "unclear"]
EmotionalState = Literal["engaged", "confused", "frustrated", "bored"]


class Diagnosis(BaseModel):
    """Structured pedagogical and cognitive diagnosis of a learner message."""

    model_config = ConfigDict(extra="forbid")

    understanding: Understanding = Field(
        ...,
        description="Assessed correctness of learner's conceptual understanding",
    )
    misconception_id: str | None = Field(
        default=None,
        description="Identified candidate misconception ID, or null if none",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )
    needs_verification: bool = Field(
        default=False,
        description="True if an explicit answer/claim requires deterministic verification",
    )
    extracted_answer: str | None = Field(
        default=None,
        description="Extracted numeric/symbolic/option answer string, if present",
    )
    emotional_state: EmotionalState = Field(
        default="engaged",
        description="Inferred emotional/engagement state of the learner",
    )
    diagnosis_fallback: bool = Field(
        default=False,
        description="True if diagnosis failed or timed out and fell back to safe default",
    )
