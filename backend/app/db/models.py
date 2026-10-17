"""Database models for Users and Curriculum Content Knowledge Graph."""

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
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


class Session(Base):
    """Dialogue session between a learner and the AI tutor on a concept."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    concept_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("concepts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user: Mapped["User"] = relationship("User")
    concept: Mapped["Concept"] = relationship("Concept")
    turns: Mapped[list["Turn"]] = relationship(
        "Turn",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Turn.created_at",
    )

    def __repr__(self) -> str:
        return f"<Session id={self.id} user_id={self.user_id} concept_id={self.concept_id!r}>"


class Turn(Base):
    """Dialogue turn within a session."""

    __tablename__ = "turns"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    diagnosis: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    strategy: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_versions: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    leak_suspected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    session: Mapped["Session"] = relationship("Session", back_populates="turns")

    def __repr__(self) -> str:
        return f"<Turn id={self.id} session_id={self.session_id} role={self.role!r}>"


class MisconceptionEvent(Base):
    """Lifecycle event tracking learner misconception detection, challenge, and resolution."""

    __tablename__ = "misconception_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    misconception_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("misconceptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    turn_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("turns.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    session: Mapped["Session"] = relationship("Session")
    user: Mapped["User"] = relationship("User")
    misconception: Mapped["Misconception"] = relationship("Misconception")
    turn: Mapped["Turn | None"] = relationship("Turn")

    def __repr__(self) -> str:
        return (
            f"<MisconceptionEvent id={self.id} misconception_id={self.misconception_id!r} "
            f"status={self.status!r}>"
        )


class Mastery(Base):
    """Concept mastery tracking per learner using Bayesian Knowledge Tracing."""

    __tablename__ = "mastery"
    __table_args__ = (PrimaryKeyConstraint("user_id", "concept_id", name="pk_mastery"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    concept_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("concepts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    p_known: Mapped[float] = mapped_column(Float, default=0.2, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )

    user: Mapped["User"] = relationship("User")
    concept: Mapped["Concept"] = relationship("Concept")

    def __repr__(self) -> str:
        return (
            f"<Mastery user_id={self.user_id} concept_id={self.concept_id!r} "
            f"p_known={self.p_known:.2f}>"
        )


class UserPreferences(Base):
    """User preferences for timezone, learning goals, and voice."""

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    daily_goal_minutes: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    voice_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferred_voice: Mapped[str] = mapped_column(String(64), default="alloy", nullable=False)
    locale: Mapped[str] = mapped_column(String(32), default="en-US", nullable=False)
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

    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<UserPreferences user_id={self.user_id} timezone={self.timezone!r}>"


class ActivityEvent(Base):
    """Idempotent audit log of learner activity events used for streaks and analytics."""

    __tablename__ = "activity_events"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "ref_id", name="uq_activity_events_user_kind_ref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ref_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<ActivityEvent id={self.id} user_id={self.user_id} "
            f"kind={self.kind!r} local_date={self.local_date}>"
        )


class UserStreakState(Base):
    """User streak state including freezes available, freezes used, and longest streak."""

    __tablename__ = "user_streak_state"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    freezes_available: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    freezes_used_dates: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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

    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<UserStreakState user_id={self.user_id} "
            f"freezes_available={self.freezes_available} longest={self.longest_streak}>"
        )


class DailyActivity(Base):
    """Materialized daily aggregate of user activity for calendars, heatmaps, and streaks."""

    __tablename__ = "daily_activity"
    __table_args__ = (
        UniqueConstraint("user_id", "local_date", name="uq_daily_activity_user_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)
    is_qualifying: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    freeze_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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

    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<DailyActivity user_id={self.user_id} local_date={self.local_date} "
            f"minutes={self.minutes} qualifying={self.is_qualifying}>"
        )
