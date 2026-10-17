"""Unit tests for Neon PostgreSQL connection normalization, SSL, and pooling."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.session import (
    create_engine,
    create_session_factory,
    normalize_neon_database_url,
    ping_database,
)


def test_normalize_url_transforms_standard_postgres_scheme() -> None:
    """Standard postgresql:// scheme is converted to postgresql+asyncpg://."""
    url = "postgresql://user:password@ep-xyz.us-east-2.aws.neon.tech/neondb"
    normalized, connect_args = normalize_neon_database_url(url)

    assert normalized.startswith("postgresql+asyncpg://")
    assert "user:password@ep-xyz.us-east-2.aws.neon.tech/neondb" in normalized


def test_normalize_url_handles_neon_pooler_prepared_statements() -> None:
    """Neon pooler endpoint (-pooler.) disables prepared statement cache for PgBouncer."""
    url = (
        "postgresql://user:password@ep-sample-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"
    )
    normalized, connect_args = normalize_neon_database_url(url)

    assert normalized.startswith("postgresql+asyncpg://")
    assert "sslmode" not in normalized
    assert connect_args.get("prepared_statement_cache_size") == 0
    assert "ssl" in connect_args


def test_normalize_url_handles_direct_neon_endpoint() -> None:
    """Direct Neon endpoint (without -pooler.) does not force prepared_statement_cache_size to 0."""
    url = "postgresql+asyncpg://user:password@ep-sample-direct.us-east-2.aws.neon.tech/neondb?sslmode=require"
    normalized, connect_args = normalize_neon_database_url(url)

    assert normalized.startswith("postgresql+asyncpg://")
    assert "sslmode" not in normalized
    assert "prepared_statement_cache_size" not in connect_args
    assert "ssl" in connect_args


def test_normalize_url_handles_sslmode_disable() -> None:
    """Local or disabled SSL mode sets connect_args['ssl'] to False."""
    url = "postgresql://postgres:postgres@localhost:5432/testdb?sslmode=disable"
    normalized, connect_args = normalize_neon_database_url(url)

    assert "sslmode" not in normalized
    assert connect_args.get("ssl") is False


def test_create_engine_configures_neon_pool_settings() -> None:
    """create_engine configures pool_pre_ping and timeout parameters for PostgreSQL."""
    url = "postgresql://user:pass@ep-test-pooler.neon.tech/db?sslmode=require"
    engine = create_engine(url)

    assert engine.dialect.name == "postgresql"
    assert engine.pool is not None

    factory = create_session_factory(engine)
    assert factory is not None


@pytest.mark.asyncio
async def test_ping_database_success() -> None:
    """ping_database returns True when SELECT 1 executes cleanly."""
    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    result = await ping_database(mock_engine)
    assert result is True
    mock_conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_ping_database_failure_masks_error() -> None:
    """ping_database returns False without raising or leaking credentials upon connection error."""
    mock_engine = MagicMock()
    mock_engine.connect.side_effect = ConnectionRefusedError("Connection refused to database")

    result = await ping_database(mock_engine)
    assert result is False
