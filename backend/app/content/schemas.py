"""Pydantic v2 schemas for YAML content validation.

Strictly enforces schema structures and forbids unknown fields (extra='forbid').
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SNAKE_CASE_REGEX = re.compile(r"^[a-z0-9_]+$")


class StrictBaseModel(BaseModel):
    """Base model forbidding all unknown/extra fields."""

    model_config = ConfigDict(extra="forbid")


class TopicSchema(StrictBaseModel):
    """Topic metadata schema (topic.yaml)."""

    schema_version: int = Field(..., ge=1)
    domain: str = Field(..., min_length=1)
    topic: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)

    @field_validator("topic")
    @classmethod
    def validate_topic_slug(cls, v: str) -> str:
        if not SNAKE_CASE_REGEX.match(v):
            raise ValueError(f"Topic '{v}' must be a valid snake_case identifier.")
        return v


class ConceptSchema(StrictBaseModel):
    """Concept item schema (concepts.yaml)."""

    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=40)
    prerequisites: list[str] = Field(default_factory=list)
    difficulty: int = Field(..., ge=1, le=5)

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        if not SNAKE_CASE_REGEX.match(v):
            raise ValueError(f"Concept id '{v}' must be a valid snake_case identifier.")
        return v

    @field_validator("prerequisites")
    @classmethod
    def validate_prerequisites_format(cls, v: list[str]) -> list[str]:
        for prereq in v:
            if not SNAKE_CASE_REGEX.match(prereq):
                raise ValueError(
                    f"Prerequisite id '{prereq}' must be a valid snake_case identifier."
                )
        return v


class MisconceptionSchema(StrictBaseModel):
    """Misconception item schema (misconceptions.yaml)."""

    id: str = Field(..., min_length=1)
    concept_id: str = Field(..., min_length=1)
    statement: str = Field(..., min_length=1)
    correct_idea: str = Field(..., min_length=1)
    conflict_prompt: str = Field(..., min_length=1)
    example_utterances: list[str] = Field(..., min_length=3)
    evidence: str | None = Field(default=None)

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        if not SNAKE_CASE_REGEX.match(v):
            raise ValueError(f"Misconception id '{v}' must be a valid snake_case identifier.")
        return v

    @field_validator("concept_id")
    @classmethod
    def validate_concept_id_format(cls, v: str) -> str:
        if not SNAKE_CASE_REGEX.match(v):
            raise ValueError(f"Concept id '{v}' must be a valid snake_case identifier.")
        return v


class AnswerSpecNumeric(StrictBaseModel):
    """Numeric answer specification."""

    value: float
    unit: str = Field(..., min_length=1)
    tolerance: float = Field(..., ge=0.0, le=1.0)


class AnswerSpecSymbolic(StrictBaseModel):
    """Symbolic mathematical answer specification."""

    expression: str = Field(..., min_length=1)


class AnswerSpecMultipleChoice(StrictBaseModel):
    """Multiple choice answer specification."""

    options: list[str] = Field(..., min_length=2)
    correct_index: int = Field(..., ge=0)

    @model_validator(mode="after")
    def validate_correct_index_in_range(self) -> "AnswerSpecMultipleChoice":
        if self.correct_index >= len(self.options):
            raise ValueError(
                f"correct_index {self.correct_index} is out of bounds for "
                f"options of length {len(self.options)}"
            )
        return self


class AnswerSpec(StrictBaseModel):
    """Polymorphic container for answer specifications."""

    kind: Literal["numeric", "symbolic", "multiple_choice"]
    numeric: AnswerSpecNumeric | None = None
    symbolic: AnswerSpecSymbolic | None = None
    multiple_choice: AnswerSpecMultipleChoice | None = None

    @model_validator(mode="after")
    def validate_kind_fields(self) -> "AnswerSpec":
        if self.kind == "numeric" and self.numeric is None:
            raise ValueError("Kind 'numeric' requires 'numeric' specification block.")
        elif self.kind == "symbolic" and self.symbolic is None:
            raise ValueError("Kind 'symbolic' requires 'symbolic' specification block.")
        elif self.kind == "multiple_choice" and self.multiple_choice is None:
            raise ValueError(
                "Kind 'multiple_choice' requires 'multiple_choice' specification block."
            )
        return self


class ProblemSchema(StrictBaseModel):
    """Problem item schema (problems.yaml)."""

    id: str = Field(..., min_length=1)
    concept_id: str = Field(..., min_length=1)
    statement: str = Field(..., min_length=1)
    difficulty: int = Field(..., ge=1, le=5)
    answer_spec: AnswerSpec

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        if not SNAKE_CASE_REGEX.match(v):
            raise ValueError(f"Problem id '{v}' must be a valid snake_case identifier.")
        return v

    @field_validator("concept_id")
    @classmethod
    def validate_concept_id_format(cls, v: str) -> str:
        if not SNAKE_CASE_REGEX.match(v):
            raise ValueError(f"Concept id '{v}' must be a valid snake_case identifier.")
        return v
