"""Integration tests for /health, /ready, Request ID propagation, and uniform error shapes."""

from typing import Any

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db, get_jwks_service, get_redis
from app.config import Settings
from app.core.security import JWKSService
from app.main import create_app


@pytest.fixture
def app_fixtures(rsa_key_pair: dict[str, Any]):
    """Application fixtures providing health check dependencies."""
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

    return app, session_factory, fake_redis


@pytest.mark.asyncio
async def test_health_endpoint_always_200(app_fixtures: Any) -> None:
    """GET /health returns 200 without checking external dependencies."""
    app, _, _ = app_fixtures
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_ready_endpoint_healthy_returns_200(app_fixtures: Any) -> None:
    """GET /ready returns 200 when both DB and Redis are operational."""
    app, _, _ = app_fixtures
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_ready_endpoint_returns_503_when_redis_down(app_fixtures: Any) -> None:
    """GET /ready returns 503 when Redis check fails."""
    app, _, _ = app_fixtures

    class FailingRedis:
        async def ping(self) -> bool:
            raise ConnectionError("Redis unreachable")

    app.dependency_overrides[get_redis] = lambda: FailingRedis()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unready"
    assert body["redis"] is False


@pytest.mark.asyncio
async def test_ready_endpoint_returns_503_when_db_down(app_fixtures: Any) -> None:
    """GET /ready returns 503 when DB check fails."""
    app, _, _ = app_fixtures

    async def failing_get_db():
        class FailingSession:
            async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
                raise ConnectionError("DB unreachable")

        yield FailingSession()

    app.dependency_overrides[get_db] = failing_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unready"
    assert body["database"] is False


@pytest.mark.asyncio
async def test_request_id_echoed_when_provided(app_fixtures: Any) -> None:
    """Provided X-Request-ID header is echoed back on the response."""
    app, _, _ = app_fixtures
    custom_req_id = "client-custom-req-id-777"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/health",
            headers={"X-Request-ID": custom_req_id},
        )

    assert response.headers.get("X-Request-ID") == custom_req_id


@pytest.mark.asyncio
async def test_error_shape_on_404(app_fixtures: Any) -> None:
    """404 Not Found returns uniform error envelope."""
    app, _, _ = app_fixtures
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/non-existent-path")

    assert response.status_code == 404
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "NOT_FOUND"
    assert "request_id" in body["error"]
    assert len(body["error"]["request_id"]) > 0


@pytest.mark.asyncio
async def test_unhandled_exception_returns_500_with_uniform_error_shape(
    app_fixtures: Any,
) -> None:
    """Unhandled exception returns 500 error envelope without exposing stack trace."""
    app, _, _ = app_fixtures

    @app.get("/test-500-trigger")
    async def trigger_error():
        raise RuntimeError("Unexpected internal crash with sensitive db details: pass=secret")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/test-500-trigger")

    assert response.status_code == 500
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "request_id" in body["error"]
    # Ensure sensitive stack trace details are not leaked to client
    assert "secret" not in body["error"]["message"]
