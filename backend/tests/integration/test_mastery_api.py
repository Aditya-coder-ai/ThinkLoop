"""Integration tests for Mastery tracking and /mastery and /me/progress API endpoints."""

import asyncio
import json
import uuid
from typing import Any

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db, get_jwks_service, get_llm_client, get_redis
from app.config import Settings
from app.core.security import JWKSService
from app.db.base import Base
from app.db.models import Concept, ConceptEdge, Mastery, MisconceptionEvent, User
from app.main import create_app
from app.services.llm import FakeLLMClient, LLMResult, TokenUsage
from app.services.mastery import MasteryService


@pytest.fixture
async def mastery_app(rsa_key_pair: dict[str, Any], tmp_path: Any):
    """Set up test app with test database, fakeredis, and seed data."""
    db_file = tmp_path / "mastery_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Seed concepts and prerequisite edge
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
            embedding=[0.01] * 1024,
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
            embedding=[0.02] * 1024,
        )
        edge = ConceptEdge(source_id="c1", target_id="c2")
        session.add_all([c1, c2, edge])
        await session.commit()

    fake_redis_client = fakeredis.aioredis.FakeRedis()
    fake_llm = FakeLLMClient()

    settings = Settings(
        DATABASE_URL=db_url,
        REDIS_URL="redis://localhost:6379/0",
        AUTH_JWKS_URL="https://auth.thinkloop.ai/.well-known/jwks.json",
        AUTH_ISSUER="https://auth.thinkloop.ai",
        AUTH_AUDIENCE="thinkloop-api",
    )
    app = create_app(settings=settings)

    mock_jwks_service = JWKSService(jwks_url=settings.auth_jwks_url)
    mock_jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    async def override_get_db():
        async with session_factory() as s:
            yield s

    async def override_get_redis():
        return fake_redis_client

    def override_get_jwks():
        return mock_jwks_service

    def override_get_llm():
        return fake_llm

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_jwks_service] = override_get_jwks
    app.dependency_overrides[get_llm_client] = override_get_llm

    yield {
        "app": app,
        "llm": fake_llm,
        "redis": fake_redis_client,
        "session_factory": session_factory,
    }

    await engine.dispose()


@pytest.mark.asyncio
async def test_unclear_or_low_confidence_does_not_update_mastery(
    mastery_app: dict[str, Any],
) -> None:
    """Mastery updates are strictly skipped when turns are non-gradable."""
    session_factory = mastery_app["session_factory"]
    mastery_service = MasteryService()
    test_user_id = uuid.uuid4()

    async with session_factory() as db:
        # Create user
        u = User(id=test_user_id, auth_id="auth_test_skip", email="skip@example.com")
        db.add(u)
        await db.commit()

        # 1. Unclear turn
        res1 = await mastery_service.record_gradable_turn(
            db=db,
            user_id=test_user_id,
            concept_id="c1",
            understanding="unclear",
            confidence=0.9,
        )
        assert res1 is None

        # 2. Low confidence turn (< 0.70)
        res2 = await mastery_service.record_gradable_turn(
            db=db,
            user_id=test_user_id,
            concept_id="c1",
            understanding="correct",
            confidence=0.55,
        )
        assert res2 is None

        # 3. Partial without verification
        res3 = await mastery_service.record_gradable_turn(
            db=db,
            user_id=test_user_id,
            concept_id="c1",
            understanding="partial",
            confidence=0.85,
        )
        assert res3 is None

        # Verify no mastery record exists in DB
        stmt = select(Mastery).where(Mastery.user_id == test_user_id)
        rows = list((await db.execute(stmt)).scalars().all())
        assert len(rows) == 0


@pytest.mark.asyncio
async def test_gradable_turn_updates_mastery_and_increases_attempts(
    mastery_app: dict[str, Any],
) -> None:
    """Confident correct/incorrect turns update mastery and increment attempt counters."""
    session_factory = mastery_app["session_factory"]
    mastery_service = MasteryService()
    test_user_id = uuid.uuid4()

    async with session_factory() as db:
        u = User(id=test_user_id, auth_id="auth_test_gradable", email="gradable@example.com")
        db.add(u)
        await db.commit()

        # Turn 1: Correct with high confidence
        res1 = await mastery_service.record_gradable_turn(
            db=db,
            user_id=test_user_id,
            concept_id="c1",
            understanding="correct",
            confidence=0.85,
        )
        assert res1 is not None
        assert res1.old_p_known == 0.20
        assert res1.new_p_known > 0.20
        assert res1.attempts == 1
        assert res1.correct is True
        p_after_turn1 = res1.new_p_known

        # Turn 2: Incorrect with high confidence
        res2 = await mastery_service.record_gradable_turn(
            db=db,
            user_id=test_user_id,
            concept_id="c1",
            understanding="incorrect",
            confidence=0.90,
        )
        assert res2 is not None
        assert res2.old_p_known == p_after_turn1
        assert res2.new_p_known < p_after_turn1
        assert res2.attempts == 2
        assert res2.correct is False

        # Turn 3: Verified correct answer overrides
        res3 = await mastery_service.record_gradable_turn(
            db=db,
            user_id=test_user_id,
            concept_id="c1",
            understanding="unclear",
            confidence=0.0,
            verified_correct=True,
        )
        assert res3 is not None
        assert res3.attempts == 3
        assert res3.correct is True


@pytest.mark.asyncio
async def test_concurrent_mastery_updates(
    mastery_app: dict[str, Any],
) -> None:
    """Concurrent updates for the same (user, concept) execute safely without row corruption."""
    session_factory = mastery_app["session_factory"]
    test_user_id = uuid.uuid4()

    async with session_factory() as db:
        u = User(id=test_user_id, auth_id="auth_test_concurrent", email="concur@example.com")
        db.add(u)
        await db.commit()

    async def update_worker(worker_id: int) -> None:
        async with session_factory() as db:
            svc = MasteryService()
            await svc.record_gradable_turn(
                db=db,
                user_id=test_user_id,
                concept_id="c1",
                understanding="correct" if worker_id % 2 == 0 else "incorrect",
                confidence=0.9,
            )

    # Launch 5 concurrent update workers
    await asyncio.gather(*(update_worker(i) for i in range(5)))

    # Verify 5 attempts are recorded accurately in the database
    async with session_factory() as db:
        stmt = select(Mastery).where(
            Mastery.user_id == test_user_id,
            Mastery.concept_id == "c1",
        )
        row = (await db.execute(stmt)).scalar_one()
        assert row.attempts == 5
        assert 0.001 <= row.p_known <= 0.999


@pytest.mark.asyncio
async def test_get_topic_mastery_endpoint(mastery_app: dict[str, Any], token_factory: Any) -> None:
    """GET /mastery returns topic graph decorated with learner masteries and edges."""
    app = mastery_app["app"]
    session_factory = mastery_app["session_factory"]
    token = token_factory(auth_id="user_mastery_api", email="mastery_api@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Fetch user created by token
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Trigger user get_or_create via /me
        me_res = await client.get("/me", headers=headers)
        user_id = uuid.UUID(me_res.json()["id"])

    # Seed mastery for c1
    async with session_factory() as db:
        m = Mastery(user_id=user_id, concept_id="c1", p_known=0.92, attempts=4)
        db.add(m)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/mastery?topic=mechanics", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["topic"] == "mechanics"

        nodes = {n["concept_id"]: n for n in data["nodes"]}
        assert "c1" in nodes
        assert "c2" in nodes
        assert nodes["c1"]["p_known"] == 0.92
        assert nodes["c1"]["attempts"] == 4
        assert nodes["c1"]["state"] == "mastered"

        # c2 has no prior mastery: default 0.20, unseen
        assert nodes["c2"]["p_known"] == 0.20
        assert nodes["c2"]["attempts"] == 0
        assert nodes["c2"]["state"] == "unseen"

        # Edges c1 -> c2
        assert len(data["edges"]) == 1
        assert data["edges"][0]["source"] == "c1"
        assert data["edges"][0]["target"] == "c2"


@pytest.mark.asyncio
async def test_mastery_user_isolation(mastery_app: dict[str, Any], token_factory: Any) -> None:
    """Learner A's mastery levels do not leak to Learner B."""
    app = mastery_app["app"]
    session_factory = mastery_app["session_factory"]
    token_a = token_factory(auth_id="user_a", email="a@example.com")
    token_b = token_factory(auth_id="user_b", email="b@example.com")

    # Get user A id
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        me_a = await client.get("/me", headers={"Authorization": f"Bearer {token_a}"})
        user_a_id = uuid.UUID(me_a.json()["id"])

    # User A masters c1
    async with session_factory() as db:
        m = Mastery(user_id=user_a_id, concept_id="c1", p_known=0.95, attempts=5)
        db.add(m)
        await db.commit()

    # User B queries topic mastery
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_b = await client.get(
            "/mastery?topic=mechanics",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res_b.status_code == 200
        nodes = {n["concept_id"]: n for n in res_b.json()["nodes"]}
        # User B must see c1 as unseen with default p_known=0.20
        assert nodes["c1"]["p_known"] == 0.20
        assert nodes["c1"]["attempts"] == 0
        assert nodes["c1"]["state"] == "unseen"


@pytest.mark.asyncio
async def test_get_me_progress_endpoint(mastery_app: dict[str, Any], token_factory: Any) -> None:
    """GET /me/progress returns aggregate concept mastery and misconception stats."""
    app = mastery_app["app"]
    session_factory = mastery_app["session_factory"]
    token = token_factory(auth_id="user_prog", email="prog@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        me_res = await client.get("/me", headers=headers)
        user_id = uuid.UUID(me_res.json()["id"])

    # Seed: 1 mastered concept, 1 learning concept
    # Seed: 2 detected misconceptions, 1 resolved misconception
    async with session_factory() as db:
        m1 = Mastery(user_id=user_id, concept_id="c1", p_known=0.88, attempts=3)
        m2 = Mastery(user_id=user_id, concept_id="c2", p_known=0.55, attempts=2)
        db.add_all([m1, m2])

        # Create session to attach misconception events
        from app.db.models import Misconception, Session

        misc1 = Misconception(
            id="m_p1",
            concept_id="c1",
            statement="Statement 1",
            correct_idea="Idea 1",
            conflict_prompt="Prompt 1",
            example_utterances=["u1", "u2", "u3"],
            schema_version=1,
            is_active=True,
            content_hash="h_mp1",
            embedding=[0.01] * 1024,
        )
        misc2 = Misconception(
            id="m_p2",
            concept_id="c1",
            statement="Statement 2",
            correct_idea="Idea 2",
            conflict_prompt="Prompt 2",
            example_utterances=["u1", "u2", "u3"],
            schema_version=1,
            is_active=True,
            content_hash="h_mp2",
            embedding=[0.01] * 1024,
        )
        db.add_all([misc1, misc2])
        await db.commit()

        sess = Session(user_id=user_id, concept_id="c1")
        db.add(sess)
        await db.commit()

        evt1 = MisconceptionEvent(
            session_id=sess.id,
            user_id=user_id,
            misconception_id="m_p1",
            status="resolved",
        )
        evt2 = MisconceptionEvent(
            session_id=sess.id,
            user_id=user_id,
            misconception_id="m_p2",
            status="detected",
        )
        db.add_all([evt1, evt2])
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/me/progress", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["concepts_mastered"] == 1
        assert data["concepts_in_progress"] == 1
        assert data["total_concepts"] == 2
        assert data["misconceptions_detected"] == 2
        assert data["misconceptions_resolved"] == 1
        assert data["resolution_rate"] == 0.50


@pytest.mark.asyncio
async def test_chat_stream_emits_mastery_update_on_gradable_turn(
    mastery_app: dict[str, Any], token_factory: Any
) -> None:
    """Chat message with confident diagnosis emits mastery_update SSE event and updates DB."""
    app = mastery_app["app"]
    llm: FakeLLMClient = mastery_app["llm"]
    session_factory = mastery_app["session_factory"]
    token = token_factory(auth_id="user_chat_mastery", email="chat_mastery@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Queue diagnoser tool response (correct, confidence 0.95)
    llm.queue_completion(
        LLMResult(
            tool_calls=[
                {
                    "name": "diagnose_learner_message",
                    "input": {
                        "understanding": "correct",
                        "confidence": 0.95,
                        "emotional_state": "engaged",
                    },
                }
            ],
            usage=TokenUsage(input_tokens=40, output_tokens=30),
        )
    )
    # Queue responder stream
    llm.queue_stream(["Excellent ", "understanding!"])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create session
        sess_res = await client.post("/sessions", json={"concept_id": "c1"}, headers=headers)
        session_id = sess_res.json()["id"]

        # Post message
        stream_res = await client.post(
            f"/sessions/{session_id}/messages",
            json={
                "content": "An object in motion remains in motion unless acted upon by net force."
            },
            headers=headers,
        )
        assert stream_res.status_code == 200

        lines = stream_res.text.strip().split("\n\n")
        events = [json.loads(line[len("data: ") :]) for line in lines if line.startswith("data: ")]
        mastery_events = [e for e in events if e.get("type") == "mastery_update"]

        # Verify mastery_update SSE event was emitted
        assert len(mastery_events) == 1
        m_data = mastery_events[0]["data"]
        assert m_data["concept_id"] == "c1"
        assert m_data["old"] == 0.20
        assert m_data["new"] > 0.20
        assert m_data["attempts"] == 1

    # Verify row was written to mastery table
    async with session_factory() as db:
        stmt = select(Mastery).where(Mastery.concept_id == "c1")
        m_row = (await db.execute(stmt)).scalar_one()
        assert m_row.attempts == 1
        assert m_row.p_known == m_data["new"]
