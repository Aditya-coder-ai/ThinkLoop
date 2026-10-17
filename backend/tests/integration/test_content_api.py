"""Integration tests for Content API endpoints."""

from typing import Any

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db, get_jwks_service, get_redis
from app.config import Settings
from app.core.security import JWKSService
from app.db.base import Base
from app.db.models import Concept, ConceptEdge, Misconception, Problem
from app.main import create_app


@pytest.fixture
async def content_api_app(rsa_key_pair: dict[str, Any], tmp_path: Any):
    """Set up test app with populated concepts, edges, misconceptions, and problems."""
    db_file = tmp_path / "api_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Seed data: c1 (prereq of c2), c2, c_inactive
    async with session_factory() as session:
        c1 = Concept(
            id="c1",
            domain="physics",
            topic="mechanics",
            title="Newton's First Law",
            description="An extensive description with more than forty characters for concept 1.",
            difficulty=1,
            schema_version=1,
            is_active=True,
            content_hash="h1",
        )
        c2 = Concept(
            id="c2",
            domain="physics",
            topic="mechanics",
            title="Newton's Second Law",
            description="An extensive description with more than forty characters for concept 2.",
            difficulty=2,
            schema_version=1,
            is_active=True,
            content_hash="h2",
        )
        c_inactive = Concept(
            id="c_inactive",
            domain="physics",
            topic="mechanics",
            title="Inactive Concept",
            description="An extensive description with more than forty characters for inactive.",
            difficulty=3,
            schema_version=1,
            is_active=False,
            content_hash="h3",
        )
        session.add_all([c1, c2, c_inactive])
        await session.flush()

        edge = ConceptEdge(
            source_id="c1",
            target_id="c2",
        )
        session.add(edge)

        m1 = Misconception(
            id="m1",
            concept_id="c1",
            statement="Motion requires continuing force",
            correct_idea="Inertia maintains constant velocity",
            conflict_prompt="What happens to a sliding puck on frictionless ice?",
            example_utterances=[
                "puck stops on ice without push",
                "force is needed to keep moving",
                "it slows down naturally",
            ],
            evidence="Halloun & Hestenes",
            schema_version=1,
            is_active=True,
            content_hash="hm1",
        )
        session.add(m1)

        p1 = Problem(
            id="p1",
            concept_id="c1",
            statement=(
                "What net force is required to keep a 5kg mass moving at 10m/s in deep space?"
            ),
            difficulty=1,
            answer_spec={
                "kind": "multiple_choice",
                "multiple_choice": {
                    "options": ["0 N", "50 N", "10 N"],
                    "correct_index": 0,
                },
            },
            schema_version=1,
            is_active=True,
            content_hash="hp1",
        )
        session.add(p1)
        await session.commit()

    settings = Settings(
        database_url=db_url,
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
    )
    app = create_app(settings=settings)

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    jwks_service = JWKSService(
        jwks_url=str(settings.auth_jwks_url),
        ttl_seconds=3600,
    )
    jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_jwks_service] = lambda: jwks_service

    yield app
    await engine.dispose()


@pytest.mark.asyncio
async def test_content_api_unauthorized_without_token(content_api_app: Any) -> None:
    """All content endpoints require authentication."""
    async with AsyncClient(
        transport=ASGITransport(app=content_api_app),
        base_url="http://test",
    ) as client:
        r1 = await client.get("/concepts")
        r2 = await client.get("/concepts/c1")
        r3 = await client.get("/topics/mechanics/graph")
        r4 = await client.get("/concepts/c2/path")
        r5 = await client.get("/problems?concept_id=c1")

    assert r1.status_code == 401
    assert r2.status_code == 401
    assert r3.status_code == 401
    assert r4.status_code == 401
    assert r5.status_code == 401


@pytest.mark.asyncio
async def test_get_concepts_list(content_api_app: Any, token_factory: Any) -> None:
    token = token_factory()
    async with AsyncClient(
        transport=ASGITransport(app=content_api_app),
        base_url="http://test",
    ) as client:
        res = await client.get(
            "/concepts?domain=physics&topic=mechanics", headers={"Authorization": f"Bearer {token}"}
        )

    assert res.status_code == 200
    items = res.json()
    assert len(items) == 2
    ids = [item["id"] for item in items]
    assert "c1" in ids
    assert "c2" in ids
    assert "c_inactive" not in ids


@pytest.mark.asyncio
async def test_get_concept_detail(content_api_app: Any, token_factory: Any) -> None:
    token = token_factory()
    async with AsyncClient(
        transport=ASGITransport(app=content_api_app),
        base_url="http://test",
    ) as client:
        # Happy path: c1
        res = await client.get("/concepts/c1", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == "c1"
        assert len(data["misconceptions"]) == 1
        assert data["misconceptions"][0]["id"] == "m1"

        # Happy path: c2 (shows c1 in prerequisites)
        res_c2 = await client.get("/concepts/c2", headers={"Authorization": f"Bearer {token}"})
        assert res_c2.status_code == 200
        assert "c1" in res_c2.json()["prerequisites"]

        # Unknown concept -> 404
        res_404 = await client.get("/concepts/ghost", headers={"Authorization": f"Bearer {token}"})
        assert res_404.status_code == 404
        assert res_404.json()["error"]["code"] == "NOT_FOUND"

        # Inactive concept -> 404
        res_inact = await client.get(
            "/concepts/c_inactive", headers={"Authorization": f"Bearer {token}"}
        )
        assert res_inact.status_code == 404


@pytest.mark.asyncio
async def test_get_topic_graph(content_api_app: Any, token_factory: Any) -> None:
    token = token_factory()
    async with AsyncClient(
        transport=ASGITransport(app=content_api_app),
        base_url="http://test",
    ) as client:
        res = await client.get(
            "/topics/mechanics/graph", headers={"Authorization": f"Bearer {token}"}
        )

    assert res.status_code == 200
    graph = res.json()
    assert "nodes" in graph
    assert "edges" in graph
    assert len(graph["nodes"]) == 2  # active nodes only
    assert graph["edges"] == [{"source": "c1", "target": "c2"}]


@pytest.mark.asyncio
async def test_get_concept_learning_path(content_api_app: Any, token_factory: Any) -> None:
    token = token_factory()
    async with AsyncClient(
        transport=ASGITransport(app=content_api_app),
        base_url="http://test",
    ) as client:
        res = await client.get("/concepts/c2/path", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    path = res.json()
    assert path["concept_id"] == "c2"
    assert path["path"] == ["c1", "c2"]


@pytest.mark.asyncio
async def test_get_problems_never_exposes_answer_spec(
    content_api_app: Any, token_factory: Any
) -> None:
    """Critical security invariant: answer_spec is stripped from problem API responses."""
    token = token_factory()
    async with AsyncClient(
        transport=ASGITransport(app=content_api_app),
        base_url="http://test",
    ) as client:
        res = await client.get(
            "/problems?concept_id=c1", headers={"Authorization": f"Bearer {token}"}
        )

    assert res.status_code == 200
    raw_json_text = res.text
    # Strict assertion: answer_spec and correct_index NEVER appear in the raw response
    assert "answer_spec" not in raw_json_text
    assert "correct_index" not in raw_json_text

    problems = res.json()
    assert len(problems) == 1
    p = problems[0]
    assert p["id"] == "p1"
    assert "statement" in p
    assert "answer_spec" not in p


@pytest.mark.asyncio
async def test_get_concepts_filtering_and_list_all_problems(
    content_api_app: Any, token_factory: Any
) -> None:
    token = token_factory()
    async with AsyncClient(
        transport=ASGITransport(app=content_api_app),
        base_url="http://test",
    ) as client:
        # Domain only filter
        r_domain = await client.get(
            "/concepts?domain=physics", headers={"Authorization": f"Bearer {token}"}
        )
        assert r_domain.status_code == 200
        assert len(r_domain.json()) == 2

        # Topic only filter
        r_topic = await client.get(
            "/concepts?topic=mechanics", headers={"Authorization": f"Bearer {token}"}
        )
        assert r_topic.status_code == 200
        assert len(r_topic.json()) == 2

        # Filter with no matches
        r_empty = await client.get(
            "/concepts?domain=chemistry", headers={"Authorization": f"Bearer {token}"}
        )
        assert r_empty.status_code == 200
        assert len(r_empty.json()) == 0

        # List problems without concept_id
        r_probs = await client.get("/problems", headers={"Authorization": f"Bearer {token}"})
        assert r_probs.status_code == 200
        assert len(r_probs.json()) == 1
        assert "answer_spec" not in r_probs.text
