"""Health and readiness probe endpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis

if TYPE_CHECKING:
    RedisClient = Redis[str]
else:
    RedisClient = Redis

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Liveness check",
    description="Confirms that the FastAPI process is alive without touching external services.",
)
async def health() -> dict[str, str]:
    """Process liveness probe."""
    return {"status": "ok"}


@router.get(
    "/ready",
    summary="Readiness check",
    description="Validates active connectivity to both PostgreSQL and Redis.",
)
async def ready(
    response: Response,
    session: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
) -> dict[str, Any]:
    """Process readiness probe validating backing services."""
    db_healthy = False
    redis_healthy = False

    # Check database
    try:
        await session.execute(text("SELECT 1"))
        db_healthy = True
    except Exception as exc:
        logger.warning("Database readiness probe failed: %s", exc)

    # Check Redis
    try:
        await redis_client.ping()
        redis_healthy = True
    except Exception as exc:
        logger.warning("Redis readiness probe failed: %s", exc)

    is_ready = db_healthy and redis_healthy
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unready",
            "database": db_healthy,
            "redis": redis_healthy,
        }

    return {
        "status": "ready",
        "database": True,
        "redis": True,
    }


@router.get(
    "/health/db",
    summary="Database connectivity check",
    description="Validates active connectivity to the PostgreSQL database with safe response.",
)
async def health_db(
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Test database connectivity with safe, non-leaking responses."""
    try:
        await session.execute(text("SELECT 1"))
        return {"database": "connected"}
    except Exception as exc:
        logger.warning("Database connectivity check failed: %s", type(exc).__name__)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"database": "disconnected", "error": "Database connectivity check failed"}

