"""Schemas for Mastery tracking, concept maps, and learner progress."""

from pydantic import BaseModel, ConfigDict, Field


class MasteryNode(BaseModel):
    """Concept node representation with Bayesian mastery assessment."""

    model_config = ConfigDict(extra="forbid")

    concept_id: str = Field(..., description="Unique concept identifier")
    title: str = Field(..., description="Human-readable concept title")
    p_known: float = Field(..., ge=0.0, le=1.0, description="Estimated mastery probability")
    attempts: int = Field(..., ge=0, description="Total gradable dialogue attempts")
    state: str = Field(..., description="Pedagogical state: unseen | learning | mastered")


class MasteryEdge(BaseModel):
    """Prerequisite edge within topic knowledge graph."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., description="Prerequisite concept ID")
    target: str = Field(..., description="Dependent concept ID")


class TopicMasteryResponse(BaseModel):
    """Full topic concept map decorated with user's mastery levels."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(..., description="Curriculum topic name")
    nodes: list[MasteryNode] = Field(default_factory=list)
    edges: list[MasteryEdge] = Field(default_factory=list)


class ProgressSummary(BaseModel):
    """Cumulative learner progress across concepts and misconceptions."""

    model_config = ConfigDict(extra="forbid")

    concepts_mastered: int = Field(..., ge=0, description="Total mastered concepts")
    concepts_in_progress: int = Field(..., ge=0, description="Total concepts currently learning")
    total_concepts: int = Field(..., ge=0, description="Total active concepts in catalog")
    misconceptions_detected: int = Field(..., ge=0, description="Distinct misconceptions detected")
    misconceptions_resolved: int = Field(..., ge=0, description="Distinct misconceptions resolved")
    resolution_rate: float = Field(..., ge=0.0, le=1.0, description="Ratio of resolved to detected")


class MasteryUpdateResult(BaseModel):
    """Payload representing a single mastery update after a gradable turn."""

    model_config = ConfigDict(extra="forbid")

    concept_id: str
    old_p_known: float
    new_p_known: float
    attempts: int
    state: str
    correct: bool
