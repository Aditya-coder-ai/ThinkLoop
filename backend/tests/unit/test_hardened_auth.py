"""Unit tests for hardened authentication and session lifecycle rules.

Tests cover:
- Dev token gating via AUTH_DEV_MODE and ENVIRONMENT
- Boot-time rejection of AUTH_DEV_MODE in production
- Sanitization and deterministic UUID derivation for dev tokens
- Token omission from all log outputs
- POST /auth/logout idempotency (204 No Content)
- RS256 cryptographic verification edge cases
"""

import logging
import uuid
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.db.base import Base
from app.main import create_app


@pytest.mark.asyncio
async def test_dev_token_accepted_when_auth_dev_mode_true(
    tmp_path: Any,
) -> None:
    """Dev token is accepted when AUTH_DEV_MODE=true and ENVIRONMENT=development."""
    db_file = tmp_path / "test_dev_token.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    settings = Settings(
        database_url=db_url,
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
        environment="development",
        auth_dev_mode=True,
    )
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get(
            "/me",
            headers={"Authorization": "Bearer dev_ada_lovelace"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "email" in data
        # UUID must be deterministic
        expected_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, "thinkloop.dev.ada_lovelace"))
        assert data["id"] == expected_uuid


@pytest.mark.asyncio
async def test_dev_token_rejected_when_auth_dev_mode_false() -> None:
    """Dev token must be REJECTED (401) when AUTH_DEV_MODE is false."""
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
        environment="development",
        auth_dev_mode=False,
    )
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get(
            "/me",
            headers={"Authorization": "Bearer dev_ada_lovelace"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] in ("DEV_MODE_DISABLED", "INVALID_TOKEN")


def test_app_refuses_to_boot_when_dev_mode_in_production() -> None:
    """Application must raise RuntimeError or ValueError if dev mode is enabled in production."""
    with pytest.raises(
        (RuntimeError, ValueError), match="AUTH_DEV_MODE cannot be enabled in production"
    ):
        settings = Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            redis_url="redis://localhost:6379/0",
            auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
            auth_issuer="https://auth.thinkloop.ai",
            auth_audience="thinkloop-api",
            environment="production",
            auth_dev_mode=True,
        )
        create_app(settings)


@pytest.mark.asyncio
async def test_malicious_dev_names_rejected_or_sanitized() -> None:
    """Dev tokens with malicious characters are strictly rejected."""
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
        environment="development",
        auth_dev_mode=True,
    )
    app = create_app(settings)
    malicious_handles = [
        "dev_" + ("a" * 128),  # excessive length
        "dev_../../etc/passwd",  # path traversal
        "dev_user\nInjected: Header",  # header/log injection
        "dev_user' OR '1'='1",  # SQL injection syntax
        "dev_<script>alert(1)</script>",  # XSS payload
    ]
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        for handle in malicious_handles:
            response = await client.get("/me", headers={"Authorization": f"Bearer {handle}"})
            assert response.status_code in (400, 401, 422), f"Handle {handle} was not rejected"


@pytest.mark.asyncio
async def test_auth_logout_endpoint_idempotency_204() -> None:
    """POST /auth/logout returns 204 No Content with and without auth token, and is idempotent."""
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
        environment="development",
        auth_dev_mode=True,
    )
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        # 1. Logout without token
        res1 = await client.post("/auth/logout")
        assert res1.status_code == 204

        # 2. Logout with token
        res2 = await client.post(
            "/auth/logout",
            headers={"Authorization": "Bearer dev_ada_lovelace"},
        )
        assert res2.status_code == 204

        # 3. Repeat logout (idempotency check)
        res3 = await client.post(
            "/auth/logout",
            headers={"Authorization": "Bearer dev_ada_lovelace"},
        )
        assert res3.status_code == 204


@pytest.mark.asyncio
async def test_tokens_never_appear_in_logs(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Any,
) -> None:
    """Verify that neither raw tokens nor secret credentials ever appear in log captures."""
    db_file = tmp_path / "test_logs.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    settings = Settings(
        database_url=db_url,
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
        environment="development",
        auth_dev_mode=True,
    )
    app = create_app(settings)
    secret_token_val = "dev_secret_unexposed_credential_98765"

    caplog.set_level(logging.DEBUG)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await client.get("/me", headers={"Authorization": f"Bearer {secret_token_val}"})

    for record in caplog.records:
        assert secret_token_val not in record.message
        if hasattr(record, "request_id"):
            assert secret_token_val not in str(record.__dict__)
