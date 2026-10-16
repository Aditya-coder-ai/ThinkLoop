"""Integration tests for GET /me and idempotent user provisioning."""

import asyncio
from typing import Any

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db, get_jwks_service, get_redis
from app.config import Settings
from app.core.security import JWKSService
from app.db.base import Base
from app.db.models import User
from app.main import create_app


@pytest.fixture
async def app_with_db(rsa_key_pair: dict[str, Any], tmp_path: Any):
    """Create test application with SQLite async database."""
    db_file = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Initialize tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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

    yield app, session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_me_creates_user_on_first_call_and_returns_same_on_second(
    app_with_db: Any,
    token_factory: Any,
) -> None:
    """GET /me provisions a user record on first request and returns the existing one."""
    app, session_factory = app_with_db
    token = token_factory(auth_id="auth0|new_user_1", email="student1@thinkloop.ai")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # First call creates
        res1 = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["email"] == "student1@thinkloop.ai"
        user_id_1 = data1["id"]

        # Second call returns existing
        res2 = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["id"] == user_id_1
        assert data2["email"] == "student1@thinkloop.ai"

    # Verify only 1 row exists in DB
    async with session_factory() as session:
        result = await session.execute(
            select(func.count(User.id)).where(User.auth_id == "auth0|new_user_1")
        )
        assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_get_me_concurrent_first_calls_produces_exactly_one_row(
    app_with_db: Any,
    token_factory: Any,
) -> None:
    """Concurrent first requests (10 parallel requests) race-safely result in exactly 1 row."""
    app, session_factory = app_with_db
    token = token_factory(auth_id="auth0|concurrent_user", email="concurrent@thinkloop.ai")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        tasks = [client.get("/me", headers={"Authorization": f"Bearer {token}"}) for _ in range(10)]
        responses = await asyncio.gather(*tasks)

    # All responses should be 200
    for r in responses:
        assert r.status_code == 200

    # All responses must return the identical user ID
    user_ids = {r.json()["id"] for r in responses}
    assert len(user_ids) == 1

    # Verify database contains exactly 1 user row
    async with session_factory() as session:
        result = await session.execute(
            select(func.count(User.id)).where(User.auth_id == "auth0|concurrent_user")
        )
        assert result.scalar_one() == 1
