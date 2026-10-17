"""Integration tests for Chat & Streaming Sessions API."""

import json
import logging
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
from app.db.models import Concept, Misconception, MisconceptionEvent, Turn, User
from app.main import create_app
from app.services.llm import FakeLLMClient, LLMResult, LLMTimeoutError, TokenUsage


@pytest.fixture
async def chat_app(rsa_key_pair: dict[str, Any], tmp_path: Any):
    """Set up test app with test database, fakeredis, and FakeLLMClient."""
    db_file = tmp_path / "chat_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Seed user, concept, and misconception
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
        session.add(c1)
        m1 = Misconception(
            id="m1",
            concept_id="c1",
            statement="Constant velocity requires constant force",
            correct_idea="Objects maintain constant velocity in the absence of net force.",
            conflict_prompt=(
                "What keeps a voyager probe moving in deep space without engines firing?"
            ),
            example_utterances=[
                "Objects need continuous force to move",
                "Engines must run to keep speed",
                "Without force everything stops",
            ],
            evidence="Halloun & Hestenes, 1985",
            schema_version=1,
            is_active=True,
            content_hash="hm1",
            embedding=[0.01] * 1024,
        )
        session.add(m1)
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

    mock_jwks_service = JWKSService(
        jwks_url=settings.auth_jwks_url,
    )
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
async def test_session_lifecycle(chat_app: dict[str, Any], token_factory: Any) -> None:
    """Create session and retrieve session details with turns."""
    app = chat_app["app"]
    token = token_factory(auth_id="user_chat_1", email="chat1@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create session
        res = await client.post("/sessions", json={"concept_id": "c1"}, headers=headers)
        assert res.status_code == 201
        data = res.json()
        assert "id" in data
        assert data["concept_id"] == "c1"
        assert data["summary"] is None
        session_id = data["id"]

        # Retrieve session
        get_res = await client.get(f"/sessions/{session_id}", headers=headers)
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["id"] == session_id
        assert get_data["turns"] == []


@pytest.mark.asyncio
async def test_cross_user_session_access_returns_404(
    chat_app: dict[str, Any], token_factory: Any
) -> None:
    """Accessing another user's session returns 404, not 403."""
    app = chat_app["app"]
    token_user1 = token_factory(auth_id="user_owner", email="owner@example.com")
    token_user2 = token_factory(auth_id="user_intruder", email="intruder@example.com")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # User 1 creates session
        res = await client.post(
            "/sessions",
            json={"concept_id": "c1"},
            headers={"Authorization": f"Bearer {token_user1}"},
        )
        assert res.status_code == 201
        session_id = res.json()["id"]

        # User 2 attempts to get User 1's session -> must be 404
        get_res = await client.get(
            f"/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token_user2}"},
        )
        assert get_res.status_code == 404
        assert get_res.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_chat_stream_and_persistence(
    chat_app: dict[str, Any], token_factory: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """Stream emits tokens then done event, persists both user and assistant turns."""
    app = chat_app["app"]
    llm: FakeLLMClient = chat_app["llm"]
    token = token_factory(auth_id="user_stream", email="stream@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    secret_message = "MySuperSecretLearnerQuery12345"
    llm.queue_stream(["Let's ", "think ", "about ", "forces."])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/sessions", json={"concept_id": "c1"}, headers=headers)
        session_id = res.json()["id"]

        caplog.clear()
        with caplog.at_level(logging.INFO):
            stream_res = await client.post(
                f"/sessions/{session_id}/messages",
                json={"content": secret_message},
                headers=headers,
            )
            assert stream_res.status_code == 200
            assert "text/event-stream" in stream_res.headers["content-type"]

            lines = stream_res.text.strip().split("\n\n")
            events: list[dict[str, Any]] = []
            for line in lines:
                if line.startswith("data: "):
                    events.append(json.loads(line[len("data: ") :]))

            token_events = [e for e in events if e.get("type") == "token"]
            done_events = [e for e in events if e.get("type") == "done"]

            assert len(token_events) == 4
            tokens_text = "".join(e["data"] for e in token_events)
            assert tokens_text == "Let's think about forces."

            assert len(done_events) == 1
            assert "turn_id" in done_events[0]["data"]

            # Verify turns are persisted in database
            get_res = await client.get(f"/sessions/{session_id}", headers=headers)
            assert get_res.status_code == 200
            turns = get_res.json()["turns"]
            assert len(turns) == 2
            assert turns[0]["role"] == "user"
            assert turns[0]["content"] == secret_message
            assert turns[1]["role"] == "assistant"
            assert turns[1]["content"] == "Let's think about forces."

            # Verify logs do NOT contain the raw secret learner message
            for record in caplog.records:
                assert secret_message not in record.getMessage()


@pytest.mark.asyncio
async def test_concurrent_message_returns_409(chat_app: dict[str, Any], token_factory: Any) -> None:
    """Concurrent message while lock is held returns 409 Conflict."""
    app = chat_app["app"]
    redis = chat_app["redis"]
    token = token_factory(auth_id="user_concurrent", email="concurrent@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/sessions", json={"concept_id": "c1"}, headers=headers)
        session_id = res.json()["id"]

        # Acquire lock in redis manually to simulate in-flight turn
        lock_key = f"chat:lock:{session_id}"
        await redis.set(lock_key, "1", ex=10)

        # Attempt sending message while lock is active
        msg_res = await client.post(
            f"/sessions/{session_id}/messages",
            json={"content": "Are you there?"},
            headers=headers,
        )
        assert msg_res.status_code == 409
        assert msg_res.json()["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_llm_timeout_emits_sse_error_and_releases_lock(
    chat_app: dict[str, Any], token_factory: Any
) -> None:
    """LLM timeout emits SSE error event, does not hang with 500, and releases lock."""
    app = chat_app["app"]
    llm: FakeLLMClient = chat_app["llm"]
    redis = chat_app["redis"]
    token = token_factory(auth_id="user_err", email="err@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    llm.queue_stream_error(LLMTimeoutError("Request timed out"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/sessions", json={"concept_id": "c1"}, headers=headers)
        session_id = res.json()["id"]

        stream_res = await client.post(
            f"/sessions/{session_id}/messages",
            json={"content": "What is inertia?"},
            headers=headers,
        )
        assert stream_res.status_code == 200
        lines = stream_res.text.strip().split("\n\n")
        events = [json.loads(line[len("data: ") :]) for line in lines if line.startswith("data: ")]
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 1
        assert error_events[0]["data"]["code"] == "LLM_TIMEOUT"

        # Lock must be released
        lock_key = f"chat:lock:{session_id}"
        assert await redis.get(lock_key) is None


@pytest.mark.asyncio
async def test_client_disconnect_persists_partial_turn(
    chat_app: dict[str, Any], token_factory: Any
) -> None:
    """Disconnecting mid-stream persists partial tutor turn with partial flag."""
    app = chat_app["app"]
    llm: FakeLLMClient = chat_app["llm"]
    token = token_factory(auth_id="user_disconnect", email="disconnect@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    llm.set_chunk_delay(0.0)
    llm.queue_stream(["Part1", "Part2", "Part3", "Part4"])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/sessions", json={"concept_id": "c1"}, headers=headers)
        session_id = uuid.UUID(res.json()["id"])

    session_factory = chat_app["session_factory"]
    async with session_factory() as db:
        user_stmt = select(User).where(User.auth_id == "user_disconnect")
        user = (await db.execute(user_stmt)).scalar_one()

        from unittest.mock import MagicMock

        from app.api.sessions import post_message
        from app.content.embedder import FakeEmbedder
        from app.content.retrieval import RetrievalService
        from app.core.diagnoser import DiagnoserService
        from app.schemas.chat import MessageRequest

        request = MagicMock()
        request.app.state.session_factory = session_factory

        retrieval_svc = await RetrievalService.from_db(session=db, embedder=FakeEmbedder())
        diagnoser = DiagnoserService(llm_client=llm, retrieval_service=retrieval_svc)

        streaming_resp = await post_message(
            session_id=session_id,
            body=MessageRequest(content="Disconnect test"),
            request=request,
            current_user=user,
            db=db,
            redis=chat_app["redis"],
            llm=llm,
            diagnoser=diagnoser,
        )
        gen = streaming_resp.body_iterator
        # Advance until first token chunk
        first_token = ""
        while "Part1" not in first_token:
            first_token = await gen.__anext__()
        assert "Part1" in first_token
        # Close generator mid-stream
        await gen.aclose()

    # Verify partial turn was saved in DB
    async with session_factory() as db:
        turns_stmt = select(Turn).where(Turn.session_id == session_id).order_by(Turn.created_at)
        turns = list((await db.execute(turns_stmt)).scalars().all())
        assert len(turns) == 2
        assert turns[1].role == "assistant"
        assert turns[1].content == "Part1"
        assert turns[1].prompt_versions is not None
        assert turns[1].prompt_versions.get("partial") is True


@pytest.mark.asyncio
async def test_chat_diagnosis_persisted_on_turn_and_records_event(
    chat_app: dict[str, Any], token_factory: Any
) -> None:
    """Diagnoser runs on learner turn, saves diagnosis JSON, and records misconception event."""
    app = chat_app["app"]
    llm: FakeLLMClient = chat_app["llm"]
    token = token_factory(auth_id="user_diag", email="diag@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Queue completion for Diagnoser tool call
    llm.queue_completion(
        LLMResult(
            tool_calls=[
                {
                    "name": "diagnose_learner_message",
                    "input": {
                        "understanding": "incorrect",
                        "misconception_id": "m1",
                        "confidence": 0.88,
                        "needs_verification": False,
                        "emotional_state": "confused",
                    },
                }
            ],
            usage=TokenUsage(input_tokens=40, output_tokens=30),
        )
    )
    # Queue stream for Responder reply
    llm.queue_stream(["Consider ", "what happens ", "without friction."])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/sessions", json={"concept_id": "c1"}, headers=headers)
        assert res.status_code == 201
        session_id = res.json()["id"]

        msg_res = await client.post(
            f"/sessions/{session_id}/messages",
            json={"content": "You need constant engine thrust to keep moving at constant speed."},
            headers=headers,
        )
        assert msg_res.status_code == 200

        # Retrieve session and verify turn
        get_res = await client.get(f"/sessions/{session_id}", headers=headers)
        assert get_res.status_code == 200
        turns = get_res.json()["turns"]
        assert len(turns) == 2

        user_turn = turns[0]
        assert user_turn["role"] == "user"
        diagnosis = user_turn["diagnosis"]
        assert diagnosis is not None
        assert diagnosis["understanding"] == "incorrect"
        assert diagnosis["misconception_id"] == "m1"
        assert diagnosis["confidence"] == 0.88
        assert diagnosis["emotional_state"] == "confused"
        assert diagnosis["diagnosis_fallback"] is False
        assert user_turn["prompt_versions"]["diagnoser"] == "diagnoser_v1"

    # Verify misconception_events row in database
    session_factory = chat_app["session_factory"]
    async with session_factory() as db:
        evt_stmt = select(MisconceptionEvent).where(
            MisconceptionEvent.session_id == uuid.UUID(session_id)
        )
        events = list((await db.execute(evt_stmt)).scalars().all())
        assert len(events) == 1
        assert events[0].misconception_id == "m1"
        assert events[0].status == "detected"
        assert events[0].turn_id == uuid.UUID(user_turn["id"])


@pytest.mark.asyncio
async def test_chat_diagnosis_fallback_when_llm_fails(
    chat_app: dict[str, Any], token_factory: Any
) -> None:
    """When FAST_MODEL returns no tool call, fallback diagnosis is persisted."""
    app = chat_app["app"]
    llm: FakeLLMClient = chat_app["llm"]
    token = token_factory(auth_id="user_fallback", email="fallback@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Diagnoser gets default completion (no tool call), responder gets stream
    llm.queue_stream(["Hello there!"])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/sessions", json={"concept_id": "c1"}, headers=headers)
        session_id = res.json()["id"]

        msg_res = await client.post(
            f"/sessions/{session_id}/messages",
            json={"content": "Hello!"},
            headers=headers,
        )
        assert msg_res.status_code == 200

        get_res = await client.get(f"/sessions/{session_id}", headers=headers)
        user_turn = get_res.json()["turns"][0]
        assert user_turn["diagnosis"] is not None
        assert user_turn["diagnosis"]["understanding"] == "unclear"
        assert user_turn["diagnosis"]["confidence"] == 0.0
        assert user_turn["diagnosis"]["diagnosis_fallback"] is True
        assert user_turn["diagnosis"]["misconception_id"] is None

    # Verify NO misconception event created
    session_factory = chat_app["session_factory"]
    async with session_factory() as db:
        evt_stmt = select(MisconceptionEvent).where(
            MisconceptionEvent.session_id == uuid.UUID(session_id)
        )
        events = list((await db.execute(evt_stmt)).scalars().all())
        assert len(events) == 0
