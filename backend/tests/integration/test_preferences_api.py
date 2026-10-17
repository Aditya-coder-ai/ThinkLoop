"""Integration tests for User Preferences API and Feature Flags."""

from typing import Any

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db, get_jwks_service, get_redis, require_feature
from app.config import Settings, get_settings
from app.core.security import JWKSService
from app.db.base import Base
from app.main import create_app


@pytest.fixture
async def preferences_app(rsa_key_pair: dict[str, Any], tmp_path: Any):
    """Set up test app with test database, fakeredis, and mock JWKS."""
    db_file = tmp_path / "pref_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    test_settings = Settings(
        database_url=db_url,
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
        environment="test",
        feature_focus=True,
        feature_battle=False,  # For flag-off test
    )

    app = create_app(test_settings)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    jwks_service = JWKSService(
        jwks_url=test_settings.auth_jwks_url,
        ttl_seconds=3600,
    )
    jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_jwks_service] = lambda: jwks_service
    app.dependency_overrides[get_settings] = lambda: test_settings

    # Route for testing feature flag dependency
    @app.get(
        "/test/flag-battle",
        dependencies=[pytest.importorskip("fastapi").Depends(require_feature("feature_battle"))],
    )
    async def flag_battle_endpoint():
        return {"status": "ok"}

    yield app

    await engine.dispose()
    await fake_redis.aclose()


@pytest.mark.asyncio
async def test_get_preferences_initializes_defaults(
    preferences_app: Any,
    token_factory: Any,
) -> None:
    token = token_factory(auth_id="user_pref_1")
    transport = ASGITransport(app=preferences_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/me/preferences", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["timezone"] == "UTC"
        assert data["daily_goal_minutes"] == 20
        assert data["voice_enabled"] is False
        assert data["preferred_voice"] == "alloy"
        assert data["locale"] == "en-US"


@pytest.mark.asyncio
async def test_update_preferences_success_and_isolation(
    preferences_app: Any,
    token_factory: Any,
) -> None:
    token1 = token_factory(auth_id="user_pref_1")
    token2 = token_factory(auth_id="user_pref_2")
    transport = ASGITransport(app=preferences_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Update user 1 to Asia/Kolkata and 45 minutes
        put_resp = await client.put(
            "/me/preferences",
            json={"timezone": "Asia/Kolkata", "daily_goal_minutes": 45, "voice_enabled": True},
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert put_resp.status_code == 200
        data1 = put_resp.json()
        assert data1["timezone"] == "Asia/Kolkata"
        assert data1["daily_goal_minutes"] == 45
        assert data1["voice_enabled"] is True

        # User 2 gets defaults (isolated)
        get_resp2 = await client.get(
            "/me/preferences", headers={"Authorization": f"Bearer {token2}"}
        )
        assert get_resp2.status_code == 200
        data2 = get_resp2.json()
        assert data2["timezone"] == "UTC"
        assert data2["daily_goal_minutes"] == 20


@pytest.mark.asyncio
async def test_update_preferences_invalid_timezone_returns_422(
    preferences_app: Any,
    token_factory: Any,
) -> None:
    token = token_factory(auth_id="user_pref_1")
    transport = ASGITransport(app=preferences_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put(
            "/me/preferences",
            json={"timezone": "Mars/Base"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_feature_flag_disabled_returns_404(
    preferences_app: Any,
    token_factory: Any,
) -> None:
    token = token_factory(auth_id="user_pref_1")
    transport = ASGITransport(app=preferences_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # feature_battle was configured as False in test_settings
        resp = await client.get("/test/flag-battle", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "FEATURE_DISABLED"
