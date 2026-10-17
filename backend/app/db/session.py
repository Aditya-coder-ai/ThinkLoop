"""Asynchronous database engine and session management with Neon PostgreSQL support."""

from __future__ import annotations

import logging
import ssl
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)


def normalize_neon_database_url(raw_url: str) -> tuple[str, dict[str, Any]]:
    """Normalize Neon and PostgreSQL connection strings for asyncpg and connection pooling.

    Handles:
    - Scheme transformation: 'postgresql://' or 'postgres://' -> 'postgresql+asyncpg://'
    - SSL handling: extracts 'sslmode' query params and maps to asyncpg connect_args
    - Neon pooler compatibility: disables prepared statement cache for '-pooler.' endpoints
    """
    clean_url = raw_url.strip()
    parsed = urlparse(clean_url)
    scheme = parsed.scheme.lower()

    # Pass through non-postgres URLs (e.g. SQLite URLs used in migration verify or test suites)
    if not scheme.startswith("postgres"):
        return clean_url, {}

    # Map synchronous schemes to asyncpg driver scheme
    if scheme in ("postgresql", "postgres"):
        scheme = "postgresql+asyncpg"

    connect_args: dict[str, Any] = {}

    # Check for Neon connection pooler (PgBouncer in transaction mode)
    hostname = (parsed.hostname or "").lower()
    if "-pooler." in hostname or "pooler" in hostname:
        # PgBouncer does not support server-side prepared statements across pooled connections
        connect_args["prepared_statement_cache_size"] = 0
        connect_args["statement_cache_size"] = 0

    # Parse and sanitize query parameters for asyncpg compatibility
    query_params = parse_qs(parsed.query)
    sslmode_vals = query_params.pop("sslmode", None)
    # Strip libpq-specific parameters unsupported by asyncpg
    for libpq_param in ("channel_binding", "gssencmode", "target_session_attrs"):
        query_params.pop(libpq_param, None)

    # Reconstruct query without unsupported asyncpg parameters
    new_query = urlencode(query_params, doseq=True)
    normalized_url = urlunparse(
        (
            scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )

    # Configure SSL context if sslmode is specified or if connecting to Neon Cloud
    if sslmode_vals or "neon.tech" in hostname:
        sslmode = sslmode_vals[0].lower() if sslmode_vals else "require"
        if sslmode in ("require", "verify-ca", "verify-full"):
            ssl_ctx = ssl.create_default_context()
            connect_args["ssl"] = ssl_ctx
        elif sslmode == "disable":
            connect_args["ssl"] = False

    return normalized_url, connect_args


def create_engine(database_url: str) -> AsyncEngine:
    """Create async SQLAlchemy engine configured for Neon PostgreSQL or SQLite."""
    normalized_url, connect_args = normalize_neon_database_url(database_url)

    engine_kwargs: dict[str, Any] = {
        "echo": False,
        "future": True,
    }

    if "postgresql+asyncpg" in normalized_url:
        # Neon PostgreSQL connection pool settings
        engine_kwargs.update(
            {
                "pool_size": 10,
                "max_overflow": 20,
                "pool_pre_ping": True,
                "pool_recycle": 300,
                "connect_args": connect_args,
            }
        )
    elif "sqlite" in normalized_url:
        engine_kwargs["connect_args"] = {"check_same_thread": False}

    return create_async_engine(normalized_url, **engine_kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create sessionmaker for generating async database sessions."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def ping_database(engine: AsyncEngine) -> bool:
    """Safely test database connectivity without leaking credentials or query details."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database connectivity check failed: %s", type(exc).__name__)
        return False
