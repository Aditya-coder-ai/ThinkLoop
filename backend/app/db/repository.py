"""Typed repository functions for database operations, profiles, and mastery progress."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Concept, LearnerMastery, Profile

logger = logging.getLogger(__name__)


async def check_db_connectivity(session: AsyncSession) -> bool:
    """Check database connectivity by executing a lightweight SELECT 1 query."""
    try:
        await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database connectivity check failed: %s", type(exc).__name__)
        return False


async def list_concepts(
    session: AsyncSession,
    domain: str | None = None,
    topic: str | None = None,
    subject: str | None = None,
) -> Sequence[Concept]:
    """List active curriculum concepts with optional domain, topic, and subject filters."""
    query = select(Concept).where(Concept.is_active.is_(True))
    if domain:
        query = query.where(Concept.domain == domain)
    if topic:
        query = query.where(Concept.topic == topic)
    if subject:
        query = query.where(Concept.subject == subject)

    query = query.order_by(Concept.id.asc())
    result = await session.execute(query)
    return result.scalars().all()


async def get_concept_by_id(session: AsyncSession, concept_id: str) -> Concept | None:
    """Fetch an active concept by unique identifier."""
    stmt = select(Concept).where(
        Concept.id == concept_id,
        Concept.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_learner_profile(session: AsyncSession, user_id: str) -> Profile | None:
    """Fetch a learner profile by authenticated user ID."""
    stmt = select(Profile).where(Profile.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_learner_profile(
    session: AsyncSession,
    user_id: str,
    display_name: str | None = None,
    learning_level: str | None = None,
    exam_target: str | None = None,
) -> Profile:
    """Create or update a learner profile safely and idempotently."""
    dialect_name = session.bind.dialect.name if session.bind else "postgresql"

    # Common values for insertion/update
    insert_values: dict[str, str | None] = {"user_id": user_id}
    if display_name is not None:
        insert_values["display_name"] = display_name
    if learning_level is not None:
        insert_values["learning_level"] = learning_level
    if exam_target is not None:
        insert_values["exam_target"] = exam_target

    update_set: dict[str, object] = {"updated_at": func.now()}
    if display_name is not None:
        update_set["display_name"] = display_name
    if learning_level is not None:
        update_set["learning_level"] = learning_level
    if exam_target is not None:
        update_set["exam_target"] = exam_target

    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = (
            pg_insert(Profile)
            .values(**insert_values)
            .on_conflict_do_update(
                index_elements=[Profile.user_id],
                set_=update_set,
            )
            .returning(Profile)
        )
        result = await session.execute(stmt)
        profile = result.scalar_one()
        await session.commit()
        await session.refresh(profile)
        return profile
    else:
        # SQLite dialect handling for local/test environments
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        stmt = (
            sqlite_insert(Profile)
            .values(**insert_values)
            .on_conflict_do_update(
                index_elements=[Profile.user_id],
                set_=update_set,
            )
            .returning(Profile)
        )
        result = await session.execute(stmt)
        profile = result.scalar_one()
        await session.commit()
        await session.refresh(profile)
        return profile


async def get_learner_mastery(
    session: AsyncSession,
    user_id: str,
    concept_id: str | None = None,
) -> Sequence[LearnerMastery]:
    """Read a learner's mastery records, optionally filtered by concept ID."""
    stmt = select(LearnerMastery).where(LearnerMastery.user_id == user_id)
    if concept_id:
        stmt = stmt.where(LearnerMastery.concept_id == concept_id)
    stmt = stmt.order_by(LearnerMastery.concept_id.asc())
    result = await session.execute(stmt)
    return result.scalars().all()


async def upsert_learner_mastery(
    session: AsyncSession,
    user_id: str,
    concept_id: str,
    mastery_score: float,
    attempts_increment: int = 1,
    last_practiced_at: datetime | None = None,
    next_review_at: datetime | None = None,
) -> LearnerMastery:
    """Upsert mastery progress without creating duplicate records for the same user and concept."""
    dialect_name = session.bind.dialect.name if session.bind else "postgresql"
    practice_time = last_practiced_at or datetime.now()

    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        insert_stmt = pg_insert(LearnerMastery).values(
            user_id=user_id,
            concept_id=concept_id,
            mastery_score=mastery_score,
            attempts=attempts_increment,
            last_practiced_at=practice_time,
            next_review_at=next_review_at,
        )

        update_dict: dict[str, object] = {
            "mastery_score": mastery_score,
            "attempts": LearnerMastery.attempts + attempts_increment,
            "last_practiced_at": practice_time,
            "updated_at": func.now(),
        }
        if next_review_at is not None:
            update_dict["next_review_at"] = next_review_at

        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[LearnerMastery.user_id, LearnerMastery.concept_id],
            set_=update_dict,
        ).returning(LearnerMastery)
        result = await session.execute(stmt)
        mastery = result.scalar_one()
        await session.commit()
        await session.refresh(mastery)
        return mastery
    else:
        # SQLite dialect handling for local/test environments
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        sqlite_insert_stmt = sqlite_insert(LearnerMastery).values(
            user_id=user_id,
            concept_id=concept_id,
            mastery_score=mastery_score,
            attempts=attempts_increment,
            last_practiced_at=practice_time,
            next_review_at=next_review_at,
        )

        update_dict = {
            "mastery_score": mastery_score,
            "attempts": LearnerMastery.attempts + attempts_increment,
            "last_practiced_at": practice_time,
            "updated_at": func.now(),
        }
        if next_review_at is not None:
            update_dict["next_review_at"] = next_review_at

        stmt = sqlite_insert_stmt.on_conflict_do_update(
            index_elements=[LearnerMastery.user_id, LearnerMastery.concept_id],
            set_=update_dict,
        ).returning(LearnerMastery)
        result = await session.execute(stmt)
        mastery = result.scalar_one()
        await session.commit()
        await session.refresh(mastery)
        return mastery
