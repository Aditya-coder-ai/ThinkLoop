"""FastAPI dependency injection providers."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING, Any

from fastapi import Depends, Header, Request
from redis.asyncio import Redis

if TYPE_CHECKING:
    RedisClient = Redis[str]
else:
    RedisClient = Redis
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.rate_limit import RateLimiter
from app.core.security import JWKSService, TokenPayload, verify_token
from app.db.models import User
from app.errors import AuthenticationError

logger = logging.getLogger(__name__)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for the duration of the request."""
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise RuntimeError("Database session factory is not configured on application state")

    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def get_redis(request: Request) -> RedisClient:
    """Retrieve shared async Redis client from application state."""
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        raise RuntimeError("Redis client is not configured on application state")
    return redis_client  # type: ignore[no-any-return]


def get_jwks_service(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> JWKSService:
    """Retrieve or initialize JWKS service singleton from application state."""
    jwks_service = getattr(request.app.state, "jwks_service", None)
    if jwks_service is None:
        jwks_service = JWKSService(
            jwks_url=str(settings.auth_jwks_url),
            ttl_seconds=settings.jwks_cache_ttl_seconds,
        )
        request.app.state.jwks_service = jwks_service
    return jwks_service


async def get_or_create_user(
    session: AsyncSession,
    payload: TokenPayload,
) -> User:
    """Idempotently and race-safely fetch or create user by auth_id."""
    dialect_name = session.bind.dialect.name if session.bind else "postgresql"

    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = (
            pg_insert(User)
            .values(auth_id=payload.auth_id, email=payload.email)
            .on_conflict_do_update(
                index_elements=[User.auth_id],
                set_={"email": payload.email, "updated_at": func.now()},
            )
            .returning(User)
        )
        result = await session.execute(stmt)
        user = result.scalar_one()
        await session.commit()
        return user
    else:
        # SQLite dialect handling for local/test environments
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        stmt = (
            sqlite_insert(User)
            .values(auth_id=payload.auth_id, email=payload.email)
            .on_conflict_do_update(
                index_elements=[User.auth_id],
                set_={"email": payload.email, "updated_at": func.now()},
            )
            .returning(User)
        )
        result = await session.execute(stmt)
        user = result.scalar_one()
        await session.commit()
        return user


async def get_current_user(
    authorization: str | None = Header(None, alias="Authorization"),
    jwks_service: JWKSService = Depends(get_jwks_service),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Validate Bearer JWT and provision/retrieve authenticated user."""
    if not authorization:
        raise AuthenticationError(
            message="Authorization header missing",
            code="UNAUTHORIZED",
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthenticationError(
            message="Invalid authorization scheme, expected 'Bearer <token>'",
            code="INVALID_AUTH_HEADER",
        )

    token = parts[1]
    payload = await verify_token(
        token=token,
        jwks_service=jwks_service,
        expected_issuer=settings.auth_issuer,
        expected_audience=settings.auth_audience,
    )

    user = await get_or_create_user(session=session, payload=payload)
    return user


def rate_limit(
    limit: int | None = None,
    window_seconds: int | None = None,
) -> Callable[..., Any]:
    """Dependency factory returning rate-limiting check per user ID or client IP."""

    async def _rate_limiter_dependency(
        request: Request,
        redis_client: RedisClient = Depends(get_redis),
        settings: Settings = Depends(get_settings),
    ) -> None:
        effective_limit = limit if limit is not None else settings.rate_limit_requests
        effective_window = (
            window_seconds if window_seconds is not None else settings.rate_limit_window_seconds
        )

        limiter = RateLimiter(
            redis_client=redis_client,
            limit=effective_limit,
            window_seconds=effective_window,
        )

        # Identify by user or client IP
        auth_header = request.headers.get("Authorization")
        identifier: str
        if auth_header and auth_header.startswith("Bearer "):
            identifier = f"token:{hash(auth_header)}"
        else:
            client_host = request.client.host if request.client else "unknown"
            identifier = f"ip:{client_host}"

        await limiter.check_rate_limit(identifier=identifier)

    return _rate_limiter_dependency
