"""Unit tests for Redis rate limiter dependency and fail-open behavior."""

from typing import Any

import fakeredis.aioredis
import pytest

from app.core.rate_limit import RateLimiter
from app.errors import RateLimitExceededError


@pytest.mark.asyncio
async def test_rate_limiter_allows_up_to_limit() -> None:
    """Rate limiter allows requests within threshold and tracks count."""
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    limiter = RateLimiter(redis_client=fake_redis, limit=3, window_seconds=60)

    # First 3 requests should pass
    await limiter.check_rate_limit(identifier="user_123")
    await limiter.check_rate_limit(identifier="user_123")
    await limiter.check_rate_limit(identifier="user_123")

    # 4th request must be rejected with 429 and Retry-After
    with pytest.raises(RateLimitExceededError) as exc_info:
        await limiter.check_rate_limit(identifier="user_123")

    err = exc_info.value
    assert err.status_code == 429
    assert err.code == "RATE_LIMIT_EXCEEDED"
    assert "Retry-After" in err.headers
    assert int(err.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_rate_limiter_fails_open_when_redis_unavailable() -> None:
    """When Redis fails or connection is dropped, rate limiting fails OPEN and logs error."""
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    # Simulate broken connection
    await fake_redis.aclose()

    class BrokenRedis:
        def pipeline(self) -> Any:
            raise ConnectionError("Redis connection refused")

    broken_limiter = RateLimiter(
        redis_client=BrokenRedis(),  # type: ignore[arg-type]
        limit=2,
        window_seconds=60,
    )

    # Must NOT raise RateLimitExceededError; must fail open
    await broken_limiter.check_rate_limit(identifier="user_456")
    await broken_limiter.check_rate_limit(identifier="user_456")
    await broken_limiter.check_rate_limit(identifier="user_456")
