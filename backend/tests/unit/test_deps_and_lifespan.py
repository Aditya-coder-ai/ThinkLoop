"""Unit tests for dependencies, database session helpers, and lifespan lifecycle."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_db,
    get_jwks_service,
    get_or_create_user,
    get_redis,
    rate_limit,
)
from app.config import Settings
from app.core.security import JWKSService, TokenPayload
from app.db.models import User
from app.db.session import create_engine, create_session_factory
from app.main import create_app


@pytest.mark.asyncio
async def test_get_db_unconfigured_raises_error() -> None:
    """get_db raises RuntimeError when session factory is absent from app state."""
    req = MagicMock(spec=Request)
    req.app.state.session_factory = None

    with pytest.raises(RuntimeError, match="Database session factory is not configured"):
        async for _ in get_db(req):
            pass


@pytest.mark.asyncio
async def test_get_db_rollback_on_exception() -> None:
    """get_db triggers session rollback on unhandled inner error."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__.return_value = mock_session

    req = MagicMock(spec=Request)
    req.app.state.session_factory = mock_factory

    gen = get_db(req)
    await anext(gen)
    with pytest.raises(ValueError, match="Boom"):
        await gen.athrow(ValueError("Boom"))

    mock_session.rollback.assert_awaited_once()


def test_get_redis_unconfigured_raises_error() -> None:
    """get_redis raises RuntimeError when redis client is absent from app state."""
    req = MagicMock(spec=Request)
    req.app.state.redis = None

    with pytest.raises(RuntimeError, match="Redis client is not configured"):
        get_redis(req)


def test_get_jwks_service_instantiates_singleton() -> None:
    """get_jwks_service creates and caches a JWKSService instance on app.state."""
    app = FastAPI()
    req = MagicMock(spec=Request)
    req.app = app

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
    )

    service1 = get_jwks_service(req, settings)
    assert isinstance(service1, JWKSService)
    assert app.state.jwks_service is service1

    service2 = get_jwks_service(req, settings)
    assert service2 is service1


@pytest.mark.asyncio
async def test_get_or_create_user_postgresql_branch() -> None:
    """Test get_or_create_user executes postgresql dialect branch."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_bind = MagicMock()
    mock_bind.dialect.name = "postgresql"
    mock_session.bind = mock_bind

    user = User(auth_id="auth0|pg_user", email="pg@thinkloop.ai")
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = user
    mock_session.execute.return_value = mock_result

    payload = TokenPayload(
        auth_id="auth0|pg_user",
        email="pg@thinkloop.ai",
        raw_claims={},
    )

    res = await get_or_create_user(mock_session, payload)
    assert res.auth_id == "auth0|pg_user"
    mock_session.commit.assert_awaited_once()


def test_db_session_factories() -> None:
    """create_engine and create_session_factory initialize valid async components."""
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    assert engine is not None
    factory = create_session_factory(engine)
    assert factory is not None


@pytest.mark.asyncio
async def test_app_lifespan_lifecycle() -> None:
    """App lifespan context initializes and closes backing resources."""
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
    )
    app = create_app(settings=settings)

    with patch.object(Redis, "from_url") as mock_redis_from_url:
        mock_redis = AsyncMock(spec=Redis)
        mock_redis_from_url.return_value = mock_redis

        # Enter lifespan
        async with app.router.lifespan_context(app):
            assert app.state.engine is not None
            assert app.state.session_factory is not None
            assert app.state.redis is mock_redis
            assert app.state.jwks_service is not None

        mock_redis.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_rate_limit_dependency_unauthenticated() -> None:
    """rate_limit identifies unauthenticated clients by IP."""
    limiter_fn = rate_limit(limit=10, window_seconds=60)
    mock_req = MagicMock(spec=Request)
    mock_req.headers = {}
    mock_req.client.host = "192.168.1.1"

    mock_redis = AsyncMock(spec=Redis)
    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock(return_value=[0, 1, 1, True, []])
    mock_redis.pipeline.return_value = mock_pipe

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
    )

    await limiter_fn(mock_req, mock_redis, settings)
    assert mock_pipe.zadd.call_count == 1
