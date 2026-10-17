"""Database models for Users and Curriculum Content Knowledge Graph."""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base

DEFAULT_EMBEDDING_DIM = 1024


class User(Base):
    """User entity tracking identity across auth providers."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    auth_id: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
        index=True,
    )
    email: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} auth_id={self.auth_id!r} email={self.email!r}>"


class Concept(Base):
    """Pedagogical concept node in curriculum knowledge graph."""

    __tablename__ = "concepts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    domain: Mapped[str] = mapped_column(String, nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(DEFAULT_EMBEDDING_DIM), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    prerequisite_edges: Mapped[list["ConceptEdge"]] = relationship(
        "ConceptEdge",
        foreign_keys="[ConceptEdge.target_id]",
        back_populates="target",
        cascade="all, delete-orphan",
    )
    dependent_edges: Mapped[list["ConceptEdge"]] = relationship(
        "ConceptEdge",
        foreign_keys="[ConceptEdge.source_id]",
        back_populates="source",
        cascade="all, delete-orphan",
    )
    misconceptions: Mapped[list["Misconception"]] = relationship(
        "Misconception",
        back_populates="concept",
        cascade="all, delete-orphan",
    )
    problems: Mapped[list["Problem"]] = relationship(
        "Problem",
        back_populates="concept",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Concept id={self.id!r} topic={self.topic!r} title={self.title!r}>"


class ConceptEdge(Base):
    """Directed prerequisite relationship edge (source is prereq of target)."""

    __tablename__ = "concept_edges"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", name="uq_concept_edges_source_target"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("concepts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("concepts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source: Mapped["Concept"] = relationship(
        "Concept", foreign_keys=[source_id], back_populates="dependent_edges"
    )
    target: Mapped["Concept"] = relationship(
        "Concept", foreign_keys=[target_id], back_populates="prerequisite_edges"
    )

    def __repr__(self) -> str:
        return f"<ConceptEdge {self.source_id!r} -> {self.target_id!r}>"


class Misconception(Base):
    """Curated misconception associated with a pedagogical concept."""

    __tablename__ = "misconceptions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    concept_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("concepts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    statement: Mapped[str] = mapped_column(String, nullable=False)
    correct_idea: Mapped[str] = mapped_column(String, nullable=False)
    conflict_prompt: Mapped[str] = mapped_column(String, nullable=False)
    example_utterances: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence: Mapped[str | None] = mapped_column(String, nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(DEFAULT_EMBEDDING_DIM), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    concept: Mapped["Concept"] = relationship("Concept", back_populates="misconceptions")

    def __repr__(self) -> str:
        return f"<Misconception id={self.id!r} concept_id={self.concept_id!r}>"


class Problem(Base):
    """Problem practice item associated with a pedagogical concept."""

    __tablename__ = "problems"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    concept_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("concepts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    statement: Mapped[str] = mapped_column(String, nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    answer_spec: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    concept: Mapped["Concept"] = relationship("Concept", back_populates="problems")

    def __repr__(self) -> str:
        return f"<Problem id={self.id!r} concept_id={self.concept_id!r}>"
