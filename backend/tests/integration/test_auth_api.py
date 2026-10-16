"""Integration tests for Authentication dependency and HTTP headers."""

from typing import Any

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db, get_jwks_service, get_redis
from app.config import Settings
from app.core.security import JWKSService
from app.db.base import Base
from app.main import create_app


@pytest.fixture
async def app_with_test_deps(rsa_key_pair: dict[str, Any]):
    """Create test application instance with injected in-memory dependencies."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
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
async def test_auth_missing_header_returns_401(app_with_test_deps: Any) -> None:
    """Request missing Authorization header returns 401 in standard error envelope."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_test_deps),
        base_url="http://test",
    ) as client:
        response = await client.get("/me")

    assert response.status_code == 401
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert "request_id" in body["error"]
    assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_auth_malformed_header_returns_401(app_with_test_deps: Any) -> None:
    """Non-Bearer or corrupted Authorization header returns 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_test_deps),
        base_url="http://test",
    ) as client:
        # Not Bearer
        resp1 = await client.get("/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert resp1.status_code == 401
        assert resp1.json()["error"]["code"] == "INVALID_AUTH_HEADER"

        # Bearer with invalid token string
        resp2 = await client.get("/me", headers={"Authorization": "Bearer not-a-jwt"})
        assert resp2.status_code == 401
        assert resp2.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_auth_valid_token_succeeds(
    app_with_test_deps: Any,
    token_factory: Any,
) -> None:
    """Valid Bearer token succeeds and returns 200 with X-Request-ID."""
    token = token_factory(auth_id="auth0|valid_123", email="user@thinkloop.ai")
    async with AsyncClient(
        transport=ASGITransport(app=app_with_test_deps),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "user@thinkloop.ai"
    assert "id" in data
    assert "created_at" in data
