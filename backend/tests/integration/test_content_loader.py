"""Integration tests for YAML -> PostgreSQL transactional, idempotent ContentLoader."""

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.content.embedder import FakeEmbedder
from app.db.base import Base


@pytest.fixture
async def content_db(tmp_path: Path):
    """Set up async test database engine with all tables created."""
    db_file = tmp_path / "content_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    # Import models so all tables are registered with Base.metadata
    import app.db.models  # noqa: F401

    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield session_factory
    await engine.dispose()


def create_sample_topic(path: Path) -> Path:
    topic_dir = path / "physics" / "mechanics"
    topic_dir.mkdir(parents=True, exist_ok=True)
    (topic_dir / "topic.yaml").write_text(
        "schema_version: 1\ndomain: physics\ntopic: mechanics\ntitle: Classical Mechanics\n"
    )
    (topic_dir / "concepts.yaml").write_text(
        "- id: c1\n"
        "  title: Concept One\n"
        "  description: An extensive description with more than forty characters.\n"
        "  prerequisites: []\n"
        "  difficulty: 1\n"
        "- id: c2\n"
        "  title: Concept Two\n"
        "  description: An extensive description with more than forty characters.\n"
        "  prerequisites: [c1]\n"
        "  difficulty: 2\n"
    )
    (topic_dir / "misconceptions.yaml").write_text(
        "- id: m1\n"
        "  concept_id: c1\n"
        "  statement: Heavy falls faster\n"
        "  correct_idea: Same acceleration\n"
        "  conflict_prompt: Drop two balls\n"
        "  example_utterances: ['u1', 'u2', 'u3']\n"
    )
    (topic_dir / "problems.yaml").write_text(
        "- id: p1\n"
        "  concept_id: c1\n"
        "  statement: Problem 1\n"
        "  difficulty: 2\n"
        "  answer_spec:\n"
        "    kind: numeric\n"
        "    numeric:\n"
        "      value: 9.8\n"
        "      unit: 'm/s^2'\n"
        "      tolerance: 0.05\n"
    )
    return topic_dir


@pytest.mark.asyncio
async def test_loader_sync_creates_rows_and_second_run_is_noop(
    content_db: Any, tmp_path: Path
) -> None:
    from app.content.loader import ContentLoader
    from app.db.models import Concept, ConceptEdge, Misconception, Problem

    content_root = tmp_path / "content"
    create_sample_topic(content_root)

    embedder = FakeEmbedder()
    loader = ContentLoader(session_factory=content_db, embedder=embedder, content_root=content_root)

    # 1. First sync creates expected rows
    report1 = await loader.sync()
    assert report1.created_concepts == 2
    assert report1.created_misconceptions == 1
    assert report1.created_problems == 1

    async with content_db() as session:
        c_count = (await session.execute(select(func.count(Concept.id)))).scalar_one()
        m_count = (await session.execute(select(func.count(Misconception.id)))).scalar_one()
        p_count = (await session.execute(select(func.count(Problem.id)))).scalar_one()
        e_count = (await session.execute(select(func.count(ConceptEdge.id)))).scalar_one()
        assert c_count == 2
        assert m_count == 1
        assert p_count == 1
        assert e_count == 1

        # Fetch original updated_at timestamp
        c1 = (await session.execute(select(Concept).where(Concept.id == "c1"))).scalar_one()
        c1_updated_at_orig = c1.updated_at

    # 2. Second sync is a no-op (0 changes, updated_at unchanged)
    report2 = await loader.sync()
    assert report2.created_concepts == 0
    assert report2.updated_concepts == 0
    assert report2.created_misconceptions == 0
    assert report2.updated_misconceptions == 0

    async with content_db() as session:
        c1_after = (await session.execute(select(Concept).where(Concept.id == "c1"))).scalar_one()
        assert c1_after.updated_at == c1_updated_at_orig


@pytest.mark.asyncio
async def test_loader_reembeds_only_modified_items(content_db: Any, tmp_path: Path) -> None:
    from app.content.loader import ContentLoader
    from app.db.models import Misconception

    content_root = tmp_path / "content"
    topic_dir = create_sample_topic(content_root)

    embedder = FakeEmbedder()
    loader = ContentLoader(session_factory=content_db, embedder=embedder, content_root=content_root)
    await loader.sync()

    embedder_calls_before = embedder.call_count

    (topic_dir / "misconceptions.yaml").write_text(
        "- id: m1\n"
        "  concept_id: c1\n"
        "  statement: Heavy falls MUCH faster\n"
        "  correct_idea: Same acceleration\n"
        "  conflict_prompt: Drop two balls\n"
        "  example_utterances: ['u1', 'u2', 'u3']\n"
    )

    report = await loader.sync()
    assert report.updated_misconceptions == 1
    assert report.updated_concepts == 0
    # Exactly one item re-embedded
    assert embedder.call_count == embedder_calls_before + 1

    async with content_db() as session:
        m1 = (
            await session.execute(select(Misconception).where(Misconception.id == "m1"))
        ).scalar_one()
        assert m1.statement == "Heavy falls MUCH faster"


@pytest.mark.asyncio
async def test_loader_soft_deletes_removed_item(content_db: Any, tmp_path: Path) -> None:
    from app.content.loader import ContentLoader
    from app.db.models import Misconception

    content_root = tmp_path / "content"
    topic_dir = create_sample_topic(content_root)

    embedder = FakeEmbedder()
    loader = ContentLoader(session_factory=content_db, embedder=embedder, content_root=content_root)
    await loader.sync()

    # Empty misconceptions file (remove m1)
    (topic_dir / "misconceptions.yaml").write_text("[]\n")

    report = await loader.sync()
    assert report.deactivated_misconceptions == 1

    # Verify soft-deleted (is_active=False) but NOT hard-deleted
    async with content_db() as session:
        m1 = (
            await session.execute(select(Misconception).where(Misconception.id == "m1"))
        ).scalar_one()
        assert not m1.is_active


@pytest.mark.asyncio
async def test_loader_dry_run_writes_nothing(content_db: Any, tmp_path: Path) -> None:
    from app.content.loader import ContentLoader
    from app.db.models import Concept

    content_root = tmp_path / "content"
    create_sample_topic(content_root)

    embedder = FakeEmbedder()
    loader = ContentLoader(session_factory=content_db, embedder=embedder, content_root=content_root)

    report = await loader.sync(dry_run=True)
    assert report.created_concepts == 2

    # Verify database is still empty
    async with content_db() as session:
        c_count = (await session.execute(select(func.count(Concept.id)))).scalar_one()
        assert c_count == 0


@pytest.mark.asyncio
async def test_loader_embedder_failure_rolls_back_everything(
    content_db: Any, tmp_path: Path
) -> None:
    from app.content.loader import ContentLoader
    from app.db.models import Concept

    content_root = tmp_path / "content"
    create_sample_topic(content_root)

    class FailingEmbedder(FakeEmbedder):
        def embed(self, _text: str) -> list[float]:
            raise RuntimeError("Embedder service crashed mid-sync")

    loader = ContentLoader(
        session_factory=content_db, embedder=FailingEmbedder(), content_root=content_root
    )

    with pytest.raises(RuntimeError):
        await loader.sync()

    # Entire transaction must have rolled back
    async with content_db() as session:
        c_count = (await session.execute(select(func.count(Concept.id)))).scalar_one()
        assert c_count == 0


@pytest.mark.asyncio
async def test_loader_sync_real_seed_content_twice_is_noop(content_db: Any) -> None:
    """Syncing real seed content twice produces zero changes and zero updated_at churn."""
    from app.content.loader import ContentLoader
    from app.db.models import Concept

    backend_dir = Path(__file__).resolve().parent.parent.parent
    content_root = backend_dir / "content"

    embedder = FakeEmbedder()
    loader = ContentLoader(session_factory=content_db, embedder=embedder, content_root=content_root)

    # First sync: creates seed content rows
    report1 = await loader.sync()
    assert report1.created_concepts == 15
    assert report1.created_edges == 16
    assert report1.created_misconceptions == 15
    assert report1.created_problems == 18

    # Capture timestamps
    async with content_db() as session:
        concepts = (await session.execute(select(Concept))).scalars().all()
        timestamps = {c.id: c.updated_at for c in concepts}
        assert len(timestamps) == 15

    # Second sync: strict no-op
    report2 = await loader.sync()
    assert report2.created_concepts == 0
    assert report2.updated_concepts == 0
    assert report2.deactivated_concepts == 0
    assert report2.created_edges == 0
    assert report2.removed_edges == 0
    assert report2.created_misconceptions == 0
    assert report2.updated_misconceptions == 0
    assert report2.deactivated_misconceptions == 0
    assert report2.created_problems == 0
    assert report2.updated_problems == 0
    assert report2.deactivated_problems == 0
    assert report2.embeddings_computed == 0

    # Verify timestamps did not change
    async with content_db() as session:
        concepts_after = (await session.execute(select(Concept))).scalars().all()
        for c in concepts_after:
            assert c.updated_at == timestamps[c.id]
