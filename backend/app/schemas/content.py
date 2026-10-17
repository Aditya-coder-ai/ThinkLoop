"""Pydantic schemas for Content API responses."""

from pydantic import BaseModel, ConfigDict


class ConceptRead(BaseModel):
    """Schema for basic concept representation."""

    id: str
    domain: str
    topic: str
    title: str
    description: str
    difficulty: int

    model_config = ConfigDict(from_attributes=True)


class MisconceptionRead(BaseModel):
    """Schema for student misconception representation."""

    id: str
    concept_id: str
    statement: str
    correct_idea: str
    conflict_prompt: str
    example_utterances: list[str]
    evidence: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ConceptDetailRead(ConceptRead):
    """Schema for concept detail with prerequisites and misconceptions."""

    prerequisites: list[str] = []
    misconceptions: list[MisconceptionRead] = []


class TopicGraphNode(BaseModel):
    """React Flow friendly node representation."""

    id: str
    label: str
    difficulty: int


class TopicGraphEdge(BaseModel):
    """React Flow friendly edge representation."""

    source: str
    target: str


class TopicGraphResponse(BaseModel):
    """Schema for topic prerequisite graph visualization."""

    nodes: list[TopicGraphNode]
    edges: list[TopicGraphEdge]


class LearningPathResponse(BaseModel):
    """Schema for ordered prerequisite learning sequence."""

    concept_id: str
    path: list[str]


class ProblemRead(BaseModel):
    """Learner-facing problem representation.

    CRITICAL SECURITY INVARIANT:
    answer_spec is strictly excluded and must never leave the server
    via learner-facing endpoints.
    """

    id: str
    concept_id: str
    statement: str
    difficulty: int

    model_config = ConfigDict(from_attributes=True)
