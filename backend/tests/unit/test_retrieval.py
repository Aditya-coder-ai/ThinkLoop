from typing import Any

import pytest


def test_retrieval_empty_query_returns_empty_list() -> None:
    from app.content.embedder import FakeEmbedder
    from app.content.retrieval import RetrievalService

    embedder = FakeEmbedder()
    service = RetrievalService(embedder=embedder)

    assert service.find_misconceptions("") == []
    assert service.find_misconceptions("   \n\t") == []
    assert service.find_concepts("") == []


def test_retrieval_sorts_by_score_descending() -> None:
    from app.content.embedder import FakeEmbedder
    from app.content.retrieval import MisconceptionRecord, RetrievalService

    embedder = FakeEmbedder(dimension=64)
    service = RetrievalService(embedder=embedder)

    # Seed mock in-memory misconception records with embeddings
    m1_text = "Heavier objects fall faster in a vacuum."
    m2_text = "Action and reaction forces cancel each other out."
    m3_text = "Motion requires a continuous active force to continue."

    records = [
        MisconceptionRecord(
            id="m1",
            concept_id="gravity",
            topic="mechanics",
            statement=m1_text,
            is_active=True,
            embedding=embedder.embed(m1_text),
        ),
        MisconceptionRecord(
            id="m2",
            concept_id="third_law",
            topic="mechanics",
            statement=m2_text,
            is_active=True,
            embedding=embedder.embed(m2_text),
        ),
        MisconceptionRecord(
            id="m3",
            concept_id="first_law",
            topic="mechanics",
            statement=m3_text,
            is_active=True,
            embedding=embedder.embed(m3_text),
        ),
    ]
    service.load_misconceptions(records)

    results = service.find_misconceptions(m1_text, k=3)
    assert len(results) == 3
    # Top match should be m1 with score close to 1.0
    assert results[0].misconception_id == "m1"
    assert results[0].score >= results[1].score >= results[2].score


def test_retrieval_excludes_inactive_rows() -> None:
    from app.content.embedder import FakeEmbedder
    from app.content.retrieval import MisconceptionRecord, RetrievalService

    embedder = FakeEmbedder(dimension=64)
    service = RetrievalService(embedder=embedder)

    active_text = "Active misconception statement"
    inactive_text = "Inactive deleted misconception statement"

    records = [
        MisconceptionRecord(
            id="m_active",
            concept_id="c1",
            topic="mechanics",
            statement=active_text,
            is_active=True,
            embedding=embedder.embed(active_text),
        ),
        MisconceptionRecord(
            id="m_inactive",
            concept_id="c1",
            topic="mechanics",
            statement=inactive_text,
            is_active=False,  # soft deleted
            embedding=embedder.embed(inactive_text),
        ),
    ]
    service.load_misconceptions(records)

    results = service.find_misconceptions(inactive_text, k=10)
    result_ids = [r.misconception_id for r in results]
    assert "m_inactive" not in result_ids


def test_retrieval_concept_prerequisite_filtering() -> None:
    from app.content.embedder import FakeEmbedder
    from app.content.retrieval import MisconceptionRecord, RetrievalService

    embedder = FakeEmbedder(dimension=64)
    service = RetrievalService(embedder=embedder)

    # c2 depends on c1 (prerequisite)
    # c3 is unrelated
    prereq_map = {"c2": ["c1"], "c1": [], "c3": []}
    service.set_prerequisite_map(prereq_map)

    m1_text = "Misconception for concept 1 (prereq)"
    m2_text = "Misconception for concept 2 (target)"
    m3_text = "Misconception for concept 3 (unrelated)"

    records = [
        MisconceptionRecord(
            id="m1",
            concept_id="c1",
            topic="mechanics",
            statement=m1_text,
            is_active=True,
            embedding=embedder.embed(m1_text),
        ),
        MisconceptionRecord(
            id="m2",
            concept_id="c2",
            topic="mechanics",
            statement=m2_text,
            is_active=True,
            embedding=embedder.embed(m2_text),
        ),
        MisconceptionRecord(
            id="m3",
            concept_id="c3",
            topic="mechanics",
            statement=m3_text,
            is_active=True,
            embedding=embedder.embed(m3_text),
        ),
    ]
    service.load_misconceptions(records)

    # With include_prereqs=True, searching under c2 returns m2 and m1, but NOT m3
    res_with_prereqs = service.find_misconceptions(
        "student statement", concept_id="c2", include_prereqs=True
    )
    res_ids = {r.misconception_id for r in res_with_prereqs}
    assert "m2" in res_ids
    assert "m1" in res_ids
    assert "m3" not in res_ids

    # With include_prereqs=False, searching under c2 returns only m2
    res_without_prereqs = service.find_misconceptions(
        "student statement", concept_id="c2", include_prereqs=False
    )
    res_ids_exact = {r.misconception_id for r in res_without_prereqs}
    assert "m2" in res_ids_exact
    assert "m1" not in res_ids_exact


def test_retrieval_find_concepts_and_topic_filter() -> None:
    from app.content.embedder import FakeEmbedder
    from app.content.retrieval import ConceptRecord, RetrievalService

    embedder = FakeEmbedder(dimension=64)
    service = RetrievalService(embedder=embedder)

    t1 = "Newton's Laws of Motion"
    t2 = "Thermodynamics and Heat"
    c_records = [
        ConceptRecord(
            id="c1",
            domain="physics",
            topic="mechanics",
            title=t1,
            is_active=True,
            embedding=embedder.embed(t1),
        ),
        ConceptRecord(
            id="c2",
            domain="physics",
            topic="thermo",
            title=t2,
            is_active=True,
            embedding=embedder.embed(t2),
        ),
        ConceptRecord(
            id="c_inact",
            domain="physics",
            topic="mechanics",
            title="Inactive Concept",
            is_active=False,
            embedding=embedder.embed("Inactive Concept"),
        ),
    ]
    service.load_concepts(c_records)

    # Search concepts
    res = service.find_concepts(t1, k=5)
    assert len(res) == 2  # c_inact excluded
    assert res[0].concept_id == "c1"

    # Filter by topic
    res_topic = service.find_concepts(t1, topic="mechanics")
    assert len(res_topic) == 1
    assert res_topic[0].concept_id == "c1"


@pytest.mark.asyncio
async def test_retrieval_load_from_db(tmp_path: Any) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.content.embedder import FakeEmbedder
    from app.content.retrieval import RetrievalService
    from app.db.base import Base
    from app.db.models import Concept, ConceptEdge, Misconception

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/retrieval_db.db", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    embedder = FakeEmbedder(dimension=64)

    async with session_factory() as session:
        c1 = Concept(
            id="c1",
            domain="physics",
            topic="mechanics",
            title="First Law",
            description="More than forty characters description of the first law.",
            difficulty=1,
            schema_version=1,
            is_active=True,
            content_hash="h1",
            embedding=embedder.embed("First Law"),
        )
        c2 = Concept(
            id="c2",
            domain="physics",
            topic="mechanics",
            title="Second Law",
            description="More than forty characters description of the second law.",
            difficulty=2,
            schema_version=1,
            is_active=True,
            content_hash="h2",
            embedding=embedder.embed("Second Law"),
        )
        session.add_all([c1, c2])
        await session.flush()

        edge = ConceptEdge(source_id="c1", target_id="c2")
        session.add(edge)

        m1 = Misconception(
            id="m1",
            concept_id="c1",
            statement="Motion requires force",
            correct_idea="Inertia",
            conflict_prompt="Puck on ice",
            example_utterances=["u1", "u2", "u3"],
            schema_version=1,
            is_active=True,
            content_hash="hm1",
            embedding=embedder.embed("Motion requires force"),
        )
        session.add(m1)
        await session.commit()

    async with session_factory() as session:
        service = await RetrievalService.from_db(session=session, embedder=embedder)
        results = service.find_misconceptions("Motion requires force", k=5)
        assert len(results) == 1
        assert results[0].misconception_id == "m1"

        c_results = service.find_concepts("First Law", k=5)
        assert len(c_results) == 2
        assert c_results[0].concept_id == "c1"

    await engine.dispose()
