"""Pytest test configuration and fixtures."""

import os
import time
from typing import Any

# Ensure test baseline environment is present
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AUTH_JWKS_URL", "https://auth.thinkloop.ai/.well-known/jwks.json")
os.environ.setdefault("AUTH_ISSUER", "https://auth.thinkloop.ai")
os.environ.setdefault("AUTH_AUDIENCE", "thinkloop-api")

import jwt
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# ---------------------------------------------------------------------------
# Cryptographic Key Generation & JWKS Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_key_pair() -> dict[str, Any]:
    """Generate a 2048-bit RSA key pair for session tests."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    # Generate JWK from public key using PyJWT / cryptography
    public_numbers = public_key.public_numbers()
    import base64

    def int_to_b64(val: int) -> str:
        s = val.to_bytes((val.bit_length() + 7) // 8, byteorder="big")
        return base64.urlsafe_b64encode(s).decode("utf-8").rstrip("=")

    kid = "test-key-primary"
    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": int_to_b64(public_numbers.n),
        "e": int_to_b64(public_numbers.e),
    }

    return {
        "kid": kid,
        "private_key": private_key,
        "public_key": public_key,
        "private_pem": private_pem,
        "public_pem": public_pem,
        "jwk": jwk,
        "jwks": {"keys": [jwk]},
    }


@pytest.fixture(scope="session")
def alternate_rsa_key_pair() -> dict[str, Any]:
    """Generate a separate RSA key pair for bad signature / rotation tests."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    public_key = private_key.public_key()
    import base64

    public_numbers = public_key.public_numbers()

    def int_to_b64(val: int) -> str:
        s = val.to_bytes((val.bit_length() + 7) // 8, byteorder="big")
        return base64.urlsafe_b64encode(s).decode("utf-8").rstrip("=")

    kid = "test-key-secondary"
    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": int_to_b64(public_numbers.n),
        "e": int_to_b64(public_numbers.e),
    }

    return {
        "kid": kid,
        "private_key": private_key,
        "public_key": public_key,
        "jwk": jwk,
        "jwks": {"keys": [jwk]},
    }


@pytest.fixture
def token_factory(rsa_key_pair: dict[str, Any]):
    """Helper factory to mint signed JWT tokens with various claims."""

    def _create_token(
        auth_id: str = "auth0|user_12345",
        email: str | None = "user@example.com",
        issuer: str = "https://auth.thinkloop.ai",
        audience: str = "thinkloop-api",
        expires_in: int = 3600,
        kid: str | None = None,
        private_key: Any = None,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        now = int(time.time())
        payload: dict[str, Any] = {
            "sub": auth_id,
            "iss": issuer,
            "aud": audience,
            "iat": now,
            "exp": now + expires_in,
        }
        if email is not None:
            payload["email"] = email
        if extra_claims:
            payload.update(extra_claims)

        headers: dict[str, Any] = {
            "kid": kid or rsa_key_pair["kid"],
            "alg": "RS256",
        }
        key_to_use = private_key or rsa_key_pair["private_key"]
        return jwt.encode(payload, key_to_use, algorithm="RS256", headers=headers)

    return _create_token
