"""Integration tests for learner profile and mastery endpoints with auth enforcement."""

from typing import Any

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db, get_jwks_service, get_redis
from app.config import Settings
from app.core.security import JWKSService
from app.db.base import Base
from app.db.models import Concept
from app.main import create_app


@pytest.fixture
async def learner_api_fixtures(rsa_key_pair: dict[str, Any]):
    """Fixtures for learner API integration tests with DB and Redis."""
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
    )
    app = create_app(settings=settings)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    jwks_service = JWKSService(
        jwks_url=str(settings.auth_jwks_url),
        ttl_seconds=3600,
    )
    jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    # Seed test concept
    async with session_factory() as session:
        concept = Concept(
            id="physics_newtons_laws",
            domain="physics",
            subject="physics",
            topic="dynamics",
            title="Newton's Laws of Motion",
            description="Detailed description of inertia, force, and action-reaction pairs.",
            difficulty=2,
            content_hash="seed_hash",
            is_active=True,
        )
        session.add(concept)
        await session.commit()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_jwks_service] = lambda: jwks_service

    yield app, session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_profile_lifecycle_and_user_isolation(
    learner_api_fixtures: Any,
    token_factory: Any,
) -> None:
    """Tests GET/PUT /me/profile, auto-creation, and user isolation."""
    app, _ = learner_api_fixtures

    user_a_token = token_factory(auth_id="user_alpha", email="alpha@example.com")
    user_b_token = token_factory(auth_id="user_beta", email="beta@example.com")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Unauthenticated request returns 401
        unauth_res = await client.get("/me/profile")
        assert unauth_res.status_code == 401

        # 2. User A profile initial query returns 404 before creation
        get_res = await client.get(
            "/me/profile", headers={"Authorization": f"Bearer {user_a_token}"}
        )
        assert get_res.status_code == 404

        # 3. User A creates profile via PUT /me/profile
        put_res = await client.put(
            "/me/profile",
            headers={"Authorization": f"Bearer {user_a_token}"},
            json={
                "display_name": "Alpha Learner",
                "learning_level": "High School",
                "exam_target": "Physics Olympiad",
            },
        )
        assert put_res.status_code == 200
        data = put_res.json()
        assert data["user_id"] == "user_alpha"
        assert data["display_name"] == "Alpha Learner"
        assert data["learning_level"] == "High School"
        assert data["exam_target"] == "Physics Olympiad"

        # 4. User B cannot see User A's profile
        user_b_res = await client.get(
            "/me/profile", headers={"Authorization": f"Bearer {user_b_token}"}
        )
        assert user_b_res.status_code == 404


@pytest.mark.asyncio
async def test_mastery_upsert_and_attempts_tracking(
    learner_api_fixtures: Any,
    token_factory: Any,
) -> None:
    """Tests POST /me/mastery idempotent upsert, attempts increment, and GET /me/mastery."""
    app, _ = learner_api_fixtures
    token = token_factory(auth_id="user_learner_1", email="learner1@example.com")
    concept_id = "physics_newtons_laws"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First practice session
        post_res1 = await client.post(
            "/me/mastery",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "concept_id": concept_id,
                "mastery_score": 0.6,
                "attempts_increment": 1,
            },
        )
        assert post_res1.status_code == 200
        m1 = post_res1.json()
        assert m1["concept_id"] == concept_id
        assert m1["mastery_score"] == 0.6
        assert m1["attempts"] == 1

        # Second practice session for same concept
        post_res2 = await client.post(
            "/me/mastery",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "concept_id": concept_id,
                "mastery_score": 0.92,
                "attempts_increment": 2,
            },
        )
        assert post_res2.status_code == 200
        m2 = post_res2.json()
        assert m2["concept_id"] == concept_id
        assert m2["mastery_score"] == 0.92
        assert m2["attempts"] == 3  # 1 + 2

        # Query all mastery records for this user
        get_res = await client.get(
            "/me/mastery",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_res.status_code == 200
        records = get_res.json()
        assert len(records) == 1
        assert records[0]["attempts"] == 3
        assert records[0]["mastery_score"] == 0.92


@pytest.mark.asyncio
async def test_mastery_invalid_concept_returns_404(
    learner_api_fixtures: Any,
    token_factory: Any,
) -> None:
    """POST /me/mastery for non-existent concept returns 404."""
    app, _ = learner_api_fixtures
    token = token_factory(auth_id="user_learner_2", email="learner2@example.com")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/me/mastery",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "concept_id": "non_existent_concept_id",
                "mastery_score": 0.5,
            },
        )
        assert res.status_code == 404
        assert "does not exist" in res.json()["error"]["message"]
