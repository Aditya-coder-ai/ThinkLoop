"""YAML -> PostgreSQL transactional, idempotent ContentLoader engine.

Synchronizes validated curriculum content into the database.
Guarantees atomic, idempotent upserts, content-hash based re-embedding,
and soft deletion (is_active=False) of removed items.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.content.embedder import Embedder
from app.content.schemas import (
    ConceptSchema,
    MisconceptionSchema,
    ProblemSchema,
    TopicSchema,
)
from app.content.validator import ContentValidator
from app.db.models import Concept, ConceptEdge, Misconception, Problem


@dataclass
class SyncReport:
    """Detailed summary of synchronization changes."""

    created_concepts: int = 0
    updated_concepts: int = 0
    deactivated_concepts: int = 0

    created_edges: int = 0
    removed_edges: int = 0

    created_misconceptions: int = 0
    updated_misconceptions: int = 0
    deactivated_misconceptions: int = 0

    created_problems: int = 0
    updated_problems: int = 0
    deactivated_problems: int = 0

    embeddings_computed: int = 0
    is_dry_run: bool = False


def compute_content_hash(data: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of a dictionary."""
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class ContentLoader:
    """Loads validated YAML content into the database."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedder: Embedder,
        content_root: Path | str,
    ) -> None:
        self.session_factory = session_factory
        self.embedder = embedder
        self.content_root = Path(content_root)

    async def sync(self, dry_run: bool = False) -> SyncReport:
        """Synchronize all YAML topics under content_root into database."""
        # 1. Validation gate: abort immediately before touching DB if invalid
        validator = ContentValidator(content_root=self.content_root)
        validation_result = validator.validate()
        if not validation_result.is_valid:
            error_msgs = "\n".join(
                f"- {e.file_path}: {e.message}" for e in validation_result.errors
            )
            raise ValueError(
                f"Content validation failed with {len(validation_result.errors)} "
                f"errors:\n{error_msgs}"
            )

        report = SyncReport(is_dry_run=dry_run)

        # 2. Discover and parse all topics
        topic_data: list[
            tuple[TopicSchema, list[ConceptSchema], list[MisconceptionSchema], list[ProblemSchema]]
        ] = []
        for topic_yaml_path in self.content_root.rglob("topic.yaml"):
            topic_dir = topic_yaml_path.parent
            import yaml

            with open(topic_yaml_path, encoding="utf-8") as f:
                topic = TopicSchema.model_validate(yaml.safe_load(f))

            concepts: list[ConceptSchema] = []
            c_path = topic_dir / "concepts.yaml"
            if c_path.exists():
                with open(c_path, encoding="utf-8") as f:
                    raw_c = yaml.safe_load(f) or []
                    concepts = [ConceptSchema.model_validate(item) for item in raw_c]

            misconceptions: list[MisconceptionSchema] = []
            m_path = topic_dir / "misconceptions.yaml"
            if m_path.exists():
                with open(m_path, encoding="utf-8") as f:
                    raw_m = yaml.safe_load(f) or []
                    misconceptions = [MisconceptionSchema.model_validate(item) for item in raw_m]

            problems: list[ProblemSchema] = []
            p_path = topic_dir / "problems.yaml"
            if p_path.exists():
                with open(p_path, encoding="utf-8") as f:
                    raw_p = yaml.safe_load(f) or []
                    problems = [ProblemSchema.model_validate(item) for item in raw_p]

            topic_data.append((topic, concepts, misconceptions, problems))

        # 3. Perform database synchronization in a single transactional unit
        async with self.session_factory() as session, session.begin():
            for topic, concepts, misconceptions, problems in topic_data:
                await self._sync_topic(
                    session=session,
                    topic=topic,
                    concepts=concepts,
                    misconceptions=misconceptions,
                    problems=problems,
                    report=report,
                )

            if dry_run:
                await session.rollback()
                return report

        return report

    async def _sync_topic(
        self,
        session: AsyncSession,
        topic: TopicSchema,
        concepts: list[ConceptSchema],
        misconceptions: list[MisconceptionSchema],
        problems: list[ProblemSchema],
        report: SyncReport,
    ) -> None:
        # A. Concepts
        existing_concepts_res = await session.execute(
            select(Concept).where(Concept.domain == topic.domain, Concept.topic == topic.topic)
        )
        existing_concepts = {c.id: c for c in existing_concepts_res.scalars().all()}
        incoming_concept_ids = {c.id for c in concepts}

        for c_schema in concepts:
            c_dict = c_schema.model_dump()
            c_hash = compute_content_hash(c_dict)

            if c_schema.id not in existing_concepts:
                # New concept -> compute embedding
                embed_text = f"{c_schema.title}: {c_schema.description}"
                embedding = await self.embedder.embed_async(embed_text)
                report.embeddings_computed += 1

                concept = Concept(
                    id=c_schema.id,
                    domain=topic.domain,
                    topic=topic.topic,
                    title=c_schema.title,
                    description=c_schema.description,
                    difficulty=c_schema.difficulty,
                    schema_version=topic.schema_version,
                    is_active=True,
                    content_hash=c_hash,
                    embedding=embedding,
                )
                session.add(concept)
                report.created_concepts += 1
                existing_concepts[c_schema.id] = concept
            else:
                concept = existing_concepts[c_schema.id]
                # Re-activate if was soft-deleted
                if not concept.is_active:
                    concept.is_active = True
                    report.updated_concepts += 1

                # Check if content changed
                if concept.content_hash != c_hash:
                    concept.title = c_schema.title
                    concept.description = c_schema.description
                    concept.difficulty = c_schema.difficulty
                    concept.schema_version = topic.schema_version
                    concept.content_hash = c_hash

                    embed_text = f"{c_schema.title}: {c_schema.description}"
                    concept.embedding = await self.embedder.embed_async(embed_text)
                    report.embeddings_computed += 1
                    report.updated_concepts += 1

        # Soft-delete removed concepts
        for c_id, concept in existing_concepts.items():
            if c_id not in incoming_concept_ids and concept.is_active:
                concept.is_active = False
                report.deactivated_concepts += 1

        await session.flush()

        # B. Concept Edges (Prerequisites)
        existing_edges_res = await session.execute(
            select(ConceptEdge)
            .join(Concept, ConceptEdge.target_id == Concept.id)
            .where(Concept.topic == topic.topic)
        )
        existing_edges = {(e.source_id, e.target_id): e for e in existing_edges_res.scalars().all()}

        incoming_edges: set[tuple[str, str]] = set()
        for c_schema in concepts:
            for prereq_id in c_schema.prerequisites:
                incoming_edges.add((prereq_id, c_schema.id))

        # Add missing edges
        for src_id, tgt_id in incoming_edges:
            if (src_id, tgt_id) not in existing_edges:
                edge = ConceptEdge(source_id=src_id, target_id=tgt_id)
                session.add(edge)
                report.created_edges += 1

        # Delete removed edges
        for (src_id, tgt_id), edge in existing_edges.items():
            if (src_id, tgt_id) not in incoming_edges:
                await session.delete(edge)
                report.removed_edges += 1

        await session.flush()

        # C. Misconceptions
        concept_ids_in_topic = list(existing_concepts.keys())
        existing_misc_res = await session.execute(
            select(Misconception).where(Misconception.concept_id.in_(concept_ids_in_topic))
        )
        existing_misconceptions = {m.id: m for m in existing_misc_res.scalars().all()}
        incoming_misc_ids = {m.id for m in misconceptions}

        for m_schema in misconceptions:
            m_dict = m_schema.model_dump()
            m_hash = compute_content_hash(m_dict)

            if m_schema.id not in existing_misconceptions:
                embed_text = f"{m_schema.statement} {' '.join(m_schema.example_utterances)}"
                embedding = await self.embedder.embed_async(embed_text)
                report.embeddings_computed += 1

                misc = Misconception(
                    id=m_schema.id,
                    concept_id=m_schema.concept_id,
                    statement=m_schema.statement,
                    correct_idea=m_schema.correct_idea,
                    conflict_prompt=m_schema.conflict_prompt,
                    example_utterances=m_schema.example_utterances,
                    evidence=m_schema.evidence,
                    schema_version=topic.schema_version,
                    is_active=True,
                    content_hash=m_hash,
                    embedding=embedding,
                )
                session.add(misc)
                report.created_misconceptions += 1
            else:
                misc = existing_misconceptions[m_schema.id]
                if not misc.is_active:
                    misc.is_active = True
                    report.updated_misconceptions += 1

                if misc.content_hash != m_hash:
                    misc.concept_id = m_schema.concept_id
                    misc.statement = m_schema.statement
                    misc.correct_idea = m_schema.correct_idea
                    misc.conflict_prompt = m_schema.conflict_prompt
                    misc.example_utterances = m_schema.example_utterances
                    misc.evidence = m_schema.evidence
                    misc.schema_version = topic.schema_version
                    misc.content_hash = m_hash

                    embed_text = f"{m_schema.statement} {' '.join(m_schema.example_utterances)}"
                    misc.embedding = await self.embedder.embed_async(embed_text)
                    report.embeddings_computed += 1
                    report.updated_misconceptions += 1

        # Soft-delete removed misconceptions
        for m_id, misc in existing_misconceptions.items():
            if m_id not in incoming_misc_ids and misc.is_active:
                misc.is_active = False
                report.deactivated_misconceptions += 1

        await session.flush()

        # D. Problems
        existing_prob_res = await session.execute(
            select(Problem).where(Problem.concept_id.in_(concept_ids_in_topic))
        )
        existing_problems = {p.id: p for p in existing_prob_res.scalars().all()}
        incoming_prob_ids = {p.id for p in problems}

        for p_schema in problems:
            p_dict = p_schema.model_dump()
            p_hash = compute_content_hash(p_dict)

            if p_schema.id not in existing_problems:
                prob = Problem(
                    id=p_schema.id,
                    concept_id=p_schema.concept_id,
                    statement=p_schema.statement,
                    difficulty=p_schema.difficulty,
                    answer_spec=p_schema.answer_spec.model_dump(),
                    schema_version=topic.schema_version,
                    is_active=True,
                    content_hash=p_hash,
                )
                session.add(prob)
                report.created_problems += 1
            else:
                prob = existing_problems[p_schema.id]
                if not prob.is_active:
                    prob.is_active = True
                    report.updated_problems += 1

                if prob.content_hash != p_hash:
                    prob.concept_id = p_schema.concept_id
                    prob.statement = p_schema.statement
                    prob.difficulty = p_schema.difficulty
                    prob.answer_spec = p_schema.answer_spec.model_dump()
                    prob.schema_version = topic.schema_version
                    prob.content_hash = p_hash
                    report.updated_problems += 1

        # Soft-delete removed problems
        for p_id, prob in existing_problems.items():
            if p_id not in incoming_prob_ids and prob.is_active:
                prob.is_active = False
                report.deactivated_problems += 1

        await session.flush()
