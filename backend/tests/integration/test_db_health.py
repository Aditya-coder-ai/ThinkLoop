"""Integration tests for /health/db endpoint success and error handling."""

from typing import Any
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db, get_jwks_service, get_redis
from app.config import Settings
from app.core.security import JWKSService
from app.main import create_app


@pytest.fixture
def health_fixtures(rsa_key_pair: dict[str, Any]):
    """Fixtures for database health endpoint testing."""
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
    )
    app = create_app(settings=settings)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
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

    return app, session_factory


@pytest.mark.asyncio
async def test_health_db_success(health_fixtures: Any) -> None:
    """GET /health/db returns 200 and {'database': 'connected'} when operational."""
    app, _ = health_fixtures
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"database": "connected"}


@pytest.mark.asyncio
async def test_health_db_failure_returns_503_and_masks_secrets(health_fixtures: Any) -> None:
    """GET /health/db returns 503 and safe message without SQL or secret leaks on failure."""
    app, _ = health_fixtures

    # Override get_db with failing session
    async def failing_get_db():
        failing_session = AsyncMock(spec=AsyncSession)
        failing_session.execute.side_effect = ConnectionRefusedError(
            "FATAL: password authentication failed for user 'secret_user'"
        )
        yield failing_session

    app.dependency_overrides[get_db] = failing_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health/db")

    assert response.status_code == 503
    body = response.json()
    assert body["database"] == "disconnected"
    assert body["error"] == "Database connectivity check failed"
    # Ensure no passwords or stack traces leaked
    assert "secret_user" not in response.text
    assert "password" not in response.text
    assert "Traceback" not in response.text
