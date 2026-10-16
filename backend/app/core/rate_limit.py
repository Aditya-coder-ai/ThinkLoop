"""Redis-backed rate limiting with graceful fail-open resilience."""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

from redis.asyncio import Redis

if TYPE_CHECKING:
    RedisClient = Redis[str]
else:
    RedisClient = Redis

from app.errors import RateLimitExceededError

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding-window rate limiter using Redis sorted sets."""

    def __init__(
        self,
        redis_client: RedisClient,
        limit: int = 60,
        window_seconds: int = 60,
        key_prefix: str = "rate_limit",
    ) -> None:
        self.redis = redis_client
        self.limit = limit
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix

    async def check_rate_limit(self, identifier: str) -> None:
        """Check whether the identifier has exceeded the allowed request quota.

        Fails OPEN if Redis is unavailable or communication fails.
        """
        key = f"{self.key_prefix}:{identifier}"
        now = time.time()
        window_start = now - self.window_seconds
        member = f"{now}:{uuid.uuid4()}"

        try:
            # Atomic sliding-window log using Redis pipeline
            pipe = self.redis.pipeline()
            # Remove timestamps outside the sliding window
            pipe.zremrangebyscore(key, 0, window_start)
            # Add current request timestamp
            pipe.zadd(key, {member: now})
            # Count elements in current window
            pipe.zcard(key)
            # Set key expiry to ensure Redis cleanup
            pipe.expire(key, self.window_seconds + 1)
            # Fetch oldest timestamp to compute exact Retry-After
            pipe.zrange(key, 0, 0, withscores=True)

            results: list[Any] = await pipe.execute()
            current_count: int = results[2]
            oldest_entries: list[tuple[bytes | str, float]] = results[4]

            if current_count > self.limit:
                retry_after = self.window_seconds
                if oldest_entries:
                    oldest_ts = oldest_entries[0][1]
                    retry_after = max(1, int((oldest_ts + self.window_seconds) - now))

                logger.warning(
                    "Rate limit exceeded for %s: %d/%d reqs. Retry-After: %ds",
                    identifier,
                    current_count,
                    self.limit,
                    retry_after,
                )
                raise RateLimitExceededError(
                    message=(
                        f"Rate limit of {self.limit} requests per {self.window_seconds}s exceeded."
                    ),
                    retry_after=retry_after,
                )

        except RateLimitExceededError:
            raise
        except Exception as exc:
            # Redis is down or network dropped -> fail OPEN but log error
            logger.error(
                "Redis unavailable during rate limit check for %s: %s. Failing open.",
                identifier,
                exc,
            )
            return
