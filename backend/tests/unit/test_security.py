"""Unit tests for JWKS fetching, caching, and RS256 JWT token verification."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

from app.core.security import JWKSService, TokenPayload, verify_token
from app.errors import AuthenticationError


@pytest.mark.asyncio
async def test_verify_valid_token(
    rsa_key_pair: dict[str, Any],
    token_factory: Any,
) -> None:
    """Valid token verified against cached JWKS returns decoded claims."""
    token = token_factory(
        auth_id="auth0|valid_user",
        email="student@thinkloop.ai",
        issuer="https://auth.thinkloop.ai",
        audience="thinkloop-api",
    )

    jwks_service = JWKSService(
        jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        ttl_seconds=3600,
    )
    # Seed cache directly with known keys
    jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    payload: TokenPayload = await verify_token(
        token=token,
        jwks_service=jwks_service,
        expected_issuer="https://auth.thinkloop.ai",
        expected_audience="thinkloop-api",
    )

    assert payload.auth_id == "auth0|valid_user"
    assert payload.email == "student@thinkloop.ai"


@pytest.mark.asyncio
async def test_verify_token_expired(
    rsa_key_pair: dict[str, Any],
    token_factory: Any,
) -> None:
    """Expired token raises AuthenticationError with EXPIRED_TOKEN code."""
    token = token_factory(expires_in=-60)
    jwks_service = JWKSService(
        jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        ttl_seconds=3600,
    )
    jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    with pytest.raises(AuthenticationError) as exc_info:
        await verify_token(
            token=token,
            jwks_service=jwks_service,
            expected_issuer="https://auth.thinkloop.ai",
            expected_audience="thinkloop-api",
        )
    assert exc_info.value.code == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_verify_token_wrong_audience(
    rsa_key_pair: dict[str, Any],
    token_factory: Any,
) -> None:
    """Token with wrong audience raises AuthenticationError."""
    token = token_factory(audience="wrong-audience")
    jwks_service = JWKSService(
        jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        ttl_seconds=3600,
    )
    jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    with pytest.raises(AuthenticationError) as exc_info:
        await verify_token(
            token=token,
            jwks_service=jwks_service,
            expected_issuer="https://auth.thinkloop.ai",
            expected_audience="thinkloop-api",
        )
    assert exc_info.value.code == "INVALID_AUDIENCE"


@pytest.mark.asyncio
async def test_verify_token_wrong_issuer(
    rsa_key_pair: dict[str, Any],
    token_factory: Any,
) -> None:
    """Token with wrong issuer raises AuthenticationError."""
    token = token_factory(issuer="https://evil-issuer.com")
    jwks_service = JWKSService(
        jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        ttl_seconds=3600,
    )
    jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    with pytest.raises(AuthenticationError) as exc_info:
        await verify_token(
            token=token,
            jwks_service=jwks_service,
            expected_issuer="https://auth.thinkloop.ai",
            expected_audience="thinkloop-api",
        )
    assert exc_info.value.code == "INVALID_ISSUER"


@pytest.mark.asyncio
async def test_verify_token_bad_signature(
    rsa_key_pair: dict[str, Any],
    alternate_rsa_key_pair: dict[str, Any],
    token_factory: Any,
) -> None:
    """Token signed by different private key than JWKS claims fails verification."""
    token = token_factory(
        kid=rsa_key_pair["kid"],
        private_key=alternate_rsa_key_pair["private_key"],
    )
    jwks_service = JWKSService(
        jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        ttl_seconds=3600,
    )
    jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    with pytest.raises(AuthenticationError) as exc_info:
        await verify_token(
            token=token,
            jwks_service=jwks_service,
            expected_issuer="https://auth.thinkloop.ai",
            expected_audience="thinkloop-api",
        )
    assert exc_info.value.code == "INVALID_SIGNATURE"


@pytest.mark.asyncio
async def test_verify_token_unknown_kid_refetches_jwks(
    rsa_key_pair: dict[str, Any],
    alternate_rsa_key_pair: dict[str, Any],
    token_factory: Any,
) -> None:
    """Unknown kid triggers exactly one refetch of JWKS; succeeds if new kid exists."""
    token = token_factory(
        kid=alternate_rsa_key_pair["kid"],
        private_key=alternate_rsa_key_pair["private_key"],
    )

    fetch_count = 0

    async def mock_fetch_jwks(_url: str) -> dict[str, Any]:
        nonlocal fetch_count
        fetch_count += 1
        return {"keys": [rsa_key_pair["jwk"], alternate_rsa_key_pair["jwk"]]}

    jwks_service = JWKSService(
        jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        ttl_seconds=3600,
        fetcher=mock_fetch_jwks,
    )
    jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    payload = await verify_token(
        token=token,
        jwks_service=jwks_service,
        expected_issuer="https://auth.thinkloop.ai",
        expected_audience="thinkloop-api",
    )

    assert payload.auth_id == "auth0|user_12345"
    assert fetch_count == 1


@pytest.mark.asyncio
async def test_verify_token_unknown_kid_not_in_refetched_jwks(
    rsa_key_pair: dict[str, Any],
    token_factory: Any,
) -> None:
    """Unknown kid still missing after one refetch raises AuthenticationError."""
    token = token_factory(kid="non-existent-kid")

    fetch_count = 0

    async def mock_fetch_jwks(_url: str) -> dict[str, Any]:
        nonlocal fetch_count
        fetch_count += 1
        return rsa_key_pair["jwks"]

    jwks_service = JWKSService(
        jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        ttl_seconds=3600,
        fetcher=mock_fetch_jwks,
    )
    jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    with pytest.raises(AuthenticationError) as exc_info:
        await verify_token(
            token=token,
            jwks_service=jwks_service,
            expected_issuer="https://auth.thinkloop.ai",
            expected_audience="thinkloop-api",
        )

    assert exc_info.value.code == "KEY_NOT_FOUND"
    assert fetch_count == 1


@pytest.mark.asyncio
async def test_verify_token_invalid_header_format(
    rsa_key_pair: dict[str, Any],
) -> None:
    """Corrupted token format raises AuthenticationError."""
    jwks_service = JWKSService(
        jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        ttl_seconds=3600,
    )
    jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    with pytest.raises(AuthenticationError) as exc:
        await verify_token("not.a.valid.jwt.token", jwks_service, "iss", "aud")
    assert exc.value.code == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_verify_token_unsupported_algorithm(
    rsa_key_pair: dict[str, Any],
) -> None:
    """Tokens using non-RS256 algorithms are rejected."""
    # Mint token with HS256
    token = jwt.encode(
        {"sub": "user_hs", "iss": "iss", "aud": "aud"},
        "super-secret-key-that-is-at-least-32-bytes-long",
        algorithm="HS256",
        headers={"kid": "test-kid"},
    )
    jwks_service = JWKSService(
        jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        ttl_seconds=3600,
    )
    jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    with pytest.raises(AuthenticationError) as exc:
        await verify_token(token, jwks_service, "iss", "aud")
    assert exc.value.code == "INVALID_ALGORITHM"


@pytest.mark.asyncio
async def test_verify_token_missing_kid(
    rsa_key_pair: dict[str, Any],
) -> None:
    """Tokens with header missing 'kid' are rejected."""
    token = jwt.encode(
        {"sub": "user_no_kid", "iss": "iss", "aud": "aud"},
        rsa_key_pair["private_key"],
        algorithm="RS256",
        # No kid in headers
    )
    jwks_service = JWKSService(
        jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        ttl_seconds=3600,
    )
    jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    with pytest.raises(AuthenticationError) as exc:
        await verify_token(token, jwks_service, "iss", "aud")
    assert exc.value.code == "MISSING_KID"


@pytest.mark.asyncio
async def test_verify_token_missing_sub(
    rsa_key_pair: dict[str, Any],
    token_factory: Any,
) -> None:
    """Tokens missing subject 'sub' are rejected."""
    token = token_factory(auth_id="")
    jwks_service = JWKSService(
        jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        ttl_seconds=3600,
    )
    jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    with pytest.raises(AuthenticationError) as exc:
        await verify_token(token, jwks_service, "https://auth.thinkloop.ai", "thinkloop-api")
    assert exc.value.code == "MISSING_SUB"


@pytest.mark.asyncio
async def test_jwks_service_cache_expiration(
    rsa_key_pair: dict[str, Any],
) -> None:
    """Expired cache triggers refresh_keys on lookup."""
    fetch_mock = AsyncMock(return_value=rsa_key_pair["jwks"])
    service = JWKSService(
        jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        ttl_seconds=10,
        fetcher=fetch_mock,
    )
    service.set_cached_keys(rsa_key_pair["jwks"])
    # Artificially age the cache
    service._last_fetched_at = datetime.now(UTC) - timedelta(seconds=20)
    assert service.is_cache_expired() is True

    await service.get_key(rsa_key_pair["kid"])
    assert fetch_mock.call_count == 1


@pytest.mark.asyncio
async def test_jwks_service_http_fetcher(
    rsa_key_pair: dict[str, Any],
) -> None:
    """Default HTTP fetcher correctly queries endpoint with httpx."""
    service = JWKSService(
        jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        ttl_seconds=3600,
    )
    mock_resp = MagicMock()
    mock_resp.json.return_value = rsa_key_pair["jwks"]
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        await service.refresh_keys()

    assert rsa_key_pair["kid"] in service._keys_cache
