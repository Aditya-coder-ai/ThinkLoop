"""Vector similarity retrieval service for concepts and misconceptions.

Supports:
- Cosine distance / similarity search using vector embeddings.
- Inactive row exclusion.
- Concept prerequisite hierarchy expansion.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.content.embedder import Embedder
from app.db.models import Concept, ConceptEdge, Misconception


@dataclass
class MisconceptionRecord:
    """In-memory representation of a misconception for retrieval."""

    id: str
    concept_id: str
    topic: str
    statement: str
    is_active: bool
    embedding: list[float]


@dataclass
class ConceptRecord:
    """In-memory representation of a concept for retrieval."""

    id: str
    domain: str
    topic: str
    title: str
    is_active: bool
    embedding: list[float]


@dataclass
class MisconceptionSearchResult:
    """Search result entry for misconception retrieval."""

    misconception_id: str
    concept_id: str
    statement: str
    score: float


@dataclass
class ConceptSearchResult:
    """Search result entry for concept retrieval."""

    concept_id: str
    title: str
    score: float


def cosine_similarity(v1: Sequence[float], v2: Sequence[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    # Bound to [0.0, 1.0]
    return max(0.0, min(1.0, float(dot)))


class RetrievalService:
    """Retrieval service for semantic matching against concepts and misconceptions."""

    def __init__(
        self,
        embedder: Embedder,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        self.embedder = embedder
        self.session_factory = session_factory
        self.session = session
        self._misconceptions: list[MisconceptionRecord] = []
        self._concepts: list[ConceptRecord] = []
        self._prereq_map: dict[str, list[str]] = {}

    @classmethod
    async def from_db(
        cls,
        session: AsyncSession,
        embedder: Embedder,
    ) -> "RetrievalService":
        """Factory method to construct and populate RetrievalService from DB."""
        service = cls(embedder=embedder, session=session)
        await service.load_from_db(session)
        return service

    def load_misconceptions(self, records: Sequence[MisconceptionRecord]) -> None:
        """Load in-memory misconception records (for tests or local cache)."""
        self._misconceptions = list(records)

    def load_concepts(self, records: Sequence[ConceptRecord]) -> None:
        """Load in-memory concept records."""
        self._concepts = list(records)

    def set_prerequisite_map(self, prereq_map: dict[str, list[str]]) -> None:
        """Set mapping of concept_id -> direct prerequisite concept ids."""
        self._prereq_map = prereq_map

    async def load_from_db(self, session: AsyncSession) -> None:
        """Load active concepts, misconceptions, and edges from the database."""
        # Active concepts
        c_stmt = select(Concept).where(Concept.is_active.is_(True), Concept.embedding.isnot(None))
        c_res = await session.execute(c_stmt)
        self._concepts = [
            ConceptRecord(
                id=c.id,
                domain=c.domain,
                topic=c.topic,
                title=c.title,
                is_active=c.is_active,
                embedding=list(c.embedding) if c.embedding is not None else [],
            )
            for c in c_res.scalars().all()
        ]

        # Active misconceptions
        m_stmt = (
            select(Misconception, Concept.topic)
            .join(Concept, Misconception.concept_id == Concept.id)
            .where(Misconception.is_active.is_(True), Misconception.embedding.isnot(None))
        )
        m_res = await session.execute(m_stmt)
        self._misconceptions = [
            MisconceptionRecord(
                id=m.id,
                concept_id=m.concept_id,
                topic=topic,
                statement=m.statement,
                is_active=m.is_active,
                embedding=list(m.embedding) if m.embedding is not None else [],
            )
            for m, topic in m_res.all()
        ]

        # Prerequisite map from edges
        e_stmt = select(ConceptEdge)
        e_res = await session.execute(e_stmt)
        self._prereq_map = {}
        for edge in e_res.scalars().all():
            self._prereq_map.setdefault(edge.target_id, []).append(edge.source_id)

    def find_misconceptions(
        self,
        text: str,
        concept_id: str | None = None,
        topic: str | None = None,
        k: int = 5,
        min_score: float | None = None,
        include_prereqs: bool = True,
    ) -> list[MisconceptionSearchResult]:
        """Search misconceptions matching student utterance text."""
        if not text or not text.strip():
            return []

        # Determine target concept filter set
        allowed_concept_ids: set[str] | None = None
        if concept_id:
            allowed_concept_ids = {concept_id}
            if include_prereqs:
                direct_prereqs = self._prereq_map.get(concept_id, [])
                allowed_concept_ids.update(direct_prereqs)

        query_embedding = self.embedder.embed(text.strip())
        results: list[MisconceptionSearchResult] = []

        for rec in self._misconceptions:
            if not rec.is_active:
                continue
            if topic and rec.topic != topic:
                continue
            if allowed_concept_ids is not None and rec.concept_id not in allowed_concept_ids:
                continue

            score = cosine_similarity(query_embedding, rec.embedding)
            if min_score is not None and score < min_score:
                continue

            results.append(
                MisconceptionSearchResult(
                    misconception_id=rec.id,
                    concept_id=rec.concept_id,
                    statement=rec.statement,
                    score=score,
                )
            )

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:k]

    def find_concepts(
        self,
        text: str,
        k: int = 5,
        topic: str | None = None,
        min_score: float | None = None,
    ) -> list[ConceptSearchResult]:
        """Search concepts matching query text."""
        if not text or not text.strip():
            return []

        query_embedding = self.embedder.embed(text.strip())
        results: list[ConceptSearchResult] = []

        for rec in self._concepts:
            if not rec.is_active:
                continue
            if topic and rec.topic != topic:
                continue

            score = cosine_similarity(query_embedding, rec.embedding)
            if min_score is not None and score < min_score:
                continue

            results.append(
                ConceptSearchResult(
                    concept_id=rec.id,
                    title=rec.title,
                    score=score,
                )
            )

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:k]
