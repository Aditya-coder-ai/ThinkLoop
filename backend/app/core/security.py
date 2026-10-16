"""Cryptographic verification of RS256 JWT tokens via cached JWKS."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

from app.errors import AuthenticationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TokenPayload:
    """Validated claims extracted from an authenticated JWT."""

    auth_id: str
    email: str | None
    raw_claims: dict[str, Any]


class JWKSService:
    """Fetches, caches, and rotates public keys from a JWKS endpoint."""

    def __init__(
        self,
        jwks_url: str,
        ttl_seconds: int = 3600,
        fetcher: (Callable[[str], Coroutine[Any, Any, dict[str, Any]]] | None) = None,
    ) -> None:
        self.jwks_url = jwks_url
        self.ttl_seconds = ttl_seconds
        self._custom_fetcher = fetcher
        self._keys_cache: dict[str, Any] = {}
        self._last_fetched_at: datetime | None = None
        self._lock = asyncio.Lock()

    def set_cached_keys(self, jwks_data: dict[str, Any]) -> None:
        """Manually populate key cache (useful for testing or initial seeding)."""
        keys: dict[str, Any] = {}
        for key_dict in jwks_data.get("keys", []):
            kid = key_dict.get("kid")
            if kid:
                keys[kid] = RSAAlgorithm.from_jwk(key_dict)
        self._keys_cache = keys
        self._last_fetched_at = datetime.now(UTC)

    async def _fetch_keys(self) -> dict[str, Any]:
        """Fetch JWKS document from endpoint or custom fetcher."""
        if self._custom_fetcher is not None:
            return await self._custom_fetcher(self.jwks_url)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(self.jwks_url)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

    async def refresh_keys(self) -> None:
        """Fetch remote JWKS and update in-memory cache."""
        data = await self._fetch_keys()
        self.set_cached_keys(data)

    def is_cache_expired(self) -> bool:
        """Check if cached keys have surpassed configured TTL."""
        if self._last_fetched_at is None:
            return True
        age = (datetime.now(UTC) - self._last_fetched_at).total_seconds()
        return age >= self.ttl_seconds

    async def get_key(self, kid: str) -> Any:
        """Lookup public key by key ID, refreshing cache on unknown key."""
        async with self._lock:
            # Refresh if empty or expired
            if not self._keys_cache or self.is_cache_expired():
                await self.refresh_keys()

            key = self._keys_cache.get(kid)
            if key is not None:
                return key

            # Unknown kid: attempt exactly one refetch in case of key rotation
            logger.info("Unknown kid '%s' encountered; refreshing JWKS", kid)
            await self.refresh_keys()
            key = self._keys_cache.get(kid)
            if key is not None:
                return key

            raise AuthenticationError(
                message=f"Key with kid '{kid}' not found in JWKS",
                code="KEY_NOT_FOUND",
            )


async def verify_token(
    token: str,
    jwks_service: JWKSService,
    expected_issuer: str,
    expected_audience: str,
) -> TokenPayload:
    """Verify an RS256 Bearer JWT against JWKS and extract user claims."""
    try:
        unverified_headers = jwt.get_unverified_header(token)
    except Exception as exc:
        raise AuthenticationError(
            message="Malformed or invalid token header",
            code="INVALID_TOKEN",
        ) from exc

    alg = unverified_headers.get("alg")
    if alg != "RS256":
        raise AuthenticationError(
            message=f"Unsupported token algorithm '{alg}', expected RS256",
            code="INVALID_ALGORITHM",
        )

    kid = unverified_headers.get("kid")
    if not kid:
        raise AuthenticationError(
            message="Token header missing 'kid' field",
            code="MISSING_KID",
        )

    public_key = await jwks_service.get_key(kid)

    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=expected_issuer,
            audience=expected_audience,
            options={
                "require": ["exp", "iss", "aud", "sub"],
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": True,
                "verify_signature": True,
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired", code="TOKEN_EXPIRED") from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthenticationError("Invalid token audience", code="INVALID_AUDIENCE") from exc
    except jwt.InvalidIssuerError as exc:
        raise AuthenticationError("Invalid token issuer", code="INVALID_ISSUER") from exc
    except jwt.InvalidSignatureError as exc:
        raise AuthenticationError("Invalid token signature", code="INVALID_SIGNATURE") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError(f"Token validation failed: {exc}", code="INVALID_TOKEN") from exc

    sub = payload.get("sub")
    if not sub:
        raise AuthenticationError("Token payload missing subject ('sub')", code="MISSING_SUB")

    return TokenPayload(
        auth_id=str(sub),
        email=payload.get("email"),
        raw_claims=payload,
    )
