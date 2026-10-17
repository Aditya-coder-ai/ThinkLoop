"""Alembic environment configuration supporting async engines."""

import asyncio
import os
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection

from app.db import models  # noqa: F401 - ensure models are registered with Base.metadata
from app.db.base import Base
from app.db.session import normalize_neon_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Retrieve database URL from env var, Settings (.env), or alembic config."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        try:
            from app.config import get_settings

            db_url = get_settings().database_url
        except Exception:
            pass
    if not db_url:
        db_url = config.get_main_option("sqlalchemy.url")
    if not db_url:
        db_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/thinkloop"
    return db_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    raw_url = get_url()
    url, _ = normalize_neon_database_url(raw_url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations within an active database connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations(url: str, connect_args: dict[str, Any]) -> None:
    """Create async engine and execute migrations asynchronously."""
    from sqlalchemy.ext.asyncio import create_async_engine

    connectable = create_async_engine(
        url,
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    raw_url = get_url()
    url, connect_args = normalize_neon_database_url(raw_url)

    if "+asyncpg" in url or "+aiosqlite" in url:
        asyncio.run(run_async_migrations(url, connect_args))
    else:
        # Standard sync connection (e.g. sync sqlite in tests)
        from sqlalchemy import create_engine

        connectable = create_engine(url, poolclass=pool.NullPool)
        with connectable.connect() as connection:
            do_run_migrations(connection)
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
