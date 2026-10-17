"""Mastery tracking and concept map service."""

import asyncio
import logging
import uuid

from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.learner_model import bkt_update, classify_mastery_state
from app.db.models import Concept, ConceptEdge, Mastery, MisconceptionEvent
from app.schemas.mastery import (
    MasteryEdge,
    MasteryNode,
    MasteryUpdateResult,
    ProgressSummary,
    TopicMasteryResponse,
)

logger = logging.getLogger(__name__)


class MasteryService:
    """Manages Bayesian Knowledge Tracing updates and mastery queries."""

    CONFIDENCE_THRESHOLD: float = 0.70

    async def record_gradable_turn(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        concept_id: str,
        understanding: str,
        confidence: float,
        verified_correct: bool | None = None,
    ) -> MasteryUpdateResult | None:
        """Process turn assessment and update learner mastery if signal is gradable.

        Gradable signals:
        - Deterministically verified result (verified_correct is True or False)
        - Confident LLM diagnosis (understanding in 'correct', 'incorrect' with confidence >= 0.7)
        - 'unclear', 'partial' (without verification), or low-confidence turns never update mastery.
        """
        is_correct: bool | None = None
        if verified_correct is not None:
            is_correct = verified_correct
        elif understanding == "correct" and confidence >= self.CONFIDENCE_THRESHOLD:
            is_correct = True
        elif understanding == "incorrect" and confidence >= self.CONFIDENCE_THRESHOLD:
            is_correct = False

        if is_correct is None:
            logger.debug(
                "Skipping mastery update for concept=%s, user=%s (understanding=%s, conf=%.2f)",
                concept_id,
                user_id,
                understanding,
                confidence,
            )
            return None

        # Concurrency-safe row-level lock or upsert with race-safe retry
        old_p = 0.20
        new_p = 0.20
        attempts = 1
        for attempt_i in range(10):
            try:
                stmt = (
                    select(Mastery)
                    .where(Mastery.user_id == user_id, Mastery.concept_id == concept_id)
                    .with_for_update()
                )
                mastery = (await db.execute(stmt)).scalar_one_or_none()

                if mastery:
                    old_p = mastery.p_known
                    new_p = bkt_update(p_known=old_p, correct=is_correct)
                    mastery.p_known = new_p
                    mastery.attempts = Mastery.attempts + 1
                    await db.commit()
                    await db.refresh(mastery)
                    attempts = mastery.attempts
                else:
                    old_p = 0.20
                    new_p = bkt_update(p_known=old_p, correct=is_correct)
                    attempts = 1
                    mastery = Mastery(
                        user_id=user_id,
                        concept_id=concept_id,
                        p_known=new_p,
                        attempts=1,
                    )
                    db.add(mastery)
                    await db.commit()
                    await db.refresh(mastery)
                break
            except IntegrityError:
                await db.rollback()
                await asyncio.sleep(0.01 * (attempt_i + 1))
            except Exception:
                await db.rollback()
                raise

        state = classify_mastery_state(p_known=new_p, attempts=attempts)
        logger.info(
            "Mastery updated for user=%s, concept=%s: %.3f -> %.3f (attempts=%d, state=%s)",
            user_id,
            concept_id,
            old_p,
            new_p,
            attempts,
            state,
        )

        return MasteryUpdateResult(
            concept_id=concept_id,
            old_p_known=old_p,
            new_p_known=new_p,
            attempts=attempts,
            state=state,
            correct=is_correct,
        )

    async def get_topic_mastery(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        topic: str,
    ) -> TopicMasteryResponse:
        """Fetch all active concepts in topic decorated with user's mastery assessment."""
        # 1. Fetch active concepts in topic
        c_stmt = (
            select(Concept)
            .where(Concept.topic == topic, Concept.is_active.is_(True))
            .order_by(Concept.id)
        )
        concepts = list((await db.execute(c_stmt)).scalars().all())
        concept_ids = [c.id for c in concepts]

        # 2. Fetch masteries for this user and these concepts
        m_stmt = select(Mastery).where(
            Mastery.user_id == user_id,
            Mastery.concept_id.in_(concept_ids),
        )
        mastery_rows = list((await db.execute(m_stmt)).scalars().all())
        mastery_map = {m.concept_id: m for m in mastery_rows}

        nodes: list[MasteryNode] = []
        for c in concepts:
            m = mastery_map.get(c.id)
            p_val = m.p_known if m else 0.20
            attempts = m.attempts if m else 0
            state = classify_mastery_state(p_known=p_val, attempts=attempts)
            nodes.append(
                MasteryNode(
                    concept_id=c.id,
                    title=c.title,
                    p_known=p_val,
                    attempts=attempts,
                    state=state,
                )
            )

        # 3. Fetch prerequisite edges
        e_stmt = select(ConceptEdge).where(
            ConceptEdge.source_id.in_(concept_ids),
            ConceptEdge.target_id.in_(concept_ids),
        )
        edges = list((await db.execute(e_stmt)).scalars().all())
        edge_nodes = [MasteryEdge(source=e.source_id, target=e.target_id) for e in edges]

        return TopicMasteryResponse(topic=topic, nodes=nodes, edges=edge_nodes)

    async def get_user_progress(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> ProgressSummary:
        """Compute cumulative user progress summary across concepts and misconceptions."""
        # Total active concepts
        tot_stmt = select(func.count(Concept.id)).where(Concept.is_active.is_(True))
        total_concepts = (await db.execute(tot_stmt)).scalar() or 0

        # Mastered concepts (p_known >= 0.85)
        mastered_stmt = select(func.count(Mastery.concept_id)).where(
            Mastery.user_id == user_id,
            Mastery.p_known >= 0.85,
        )
        concepts_mastered = (await db.execute(mastered_stmt)).scalar() or 0

        # Concepts in progress (attempts > 0 and p_known < 0.85)
        learning_stmt = select(func.count(Mastery.concept_id)).where(
            Mastery.user_id == user_id,
            Mastery.attempts > 0,
            Mastery.p_known < 0.85,
        )
        concepts_in_progress = (await db.execute(learning_stmt)).scalar() or 0

        # Misconceptions detected (distinct misconception_id)
        det_stmt = select(func.count(distinct(MisconceptionEvent.misconception_id))).where(
            MisconceptionEvent.user_id == user_id,
            MisconceptionEvent.status.in_(["detected", "challenged", "resolved"]),
        )
        misconceptions_detected = (await db.execute(det_stmt)).scalar() or 0

        # Misconceptions resolved
        res_stmt = select(func.count(distinct(MisconceptionEvent.misconception_id))).where(
            MisconceptionEvent.user_id == user_id,
            MisconceptionEvent.status == "resolved",
        )
        misconceptions_resolved = (await db.execute(res_stmt)).scalar() or 0

        resolution_rate = (
            float(misconceptions_resolved) / float(misconceptions_detected)
            if misconceptions_detected > 0
            else 0.0
        )

        return ProgressSummary(
            concepts_mastered=concepts_mastered,
            concepts_in_progress=concepts_in_progress,
            total_concepts=total_concepts,
            misconceptions_detected=misconceptions_detected,
            misconceptions_resolved=misconceptions_resolved,
            resolution_rate=round(resolution_rate, 4),
        )
