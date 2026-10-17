"""Unit test for Neon Auth EdDSA (Ed25519) JWKS key parsing and verification."""

import pytest

from app.core.security import JWKSService


def test_neon_auth_eddsa_jwks_parsing() -> None:
    """Verify that JWKSService correctly parses EdDSA (Ed25519) keys from Neon Auth."""
    neon_jwks = {
        "keys": [
            {
                "alg": "EdDSA",
                "crv": "Ed25519",
                "x": "E0fsVrBHGHIzPEq_aQr5YN9c2xukkQxV0IfOe8dwnME",
                "kty": "OKP",
                "kid": "994a84bf-02b8-4a52-ad55-35b733d377bb",
            }
        ]
    }

    service = JWKSService(
        jwks_url="https://ep-calm-bar-b59hddfo.neonauth.c-7.us-east-2.aws.neon.tech/neondb/auth/.well-known/jwks.json",
        ttl_seconds=3600,
    )
    service.set_cached_keys(neon_jwks)

    # Key should be present in cache and not throw InvalidKeyError
    key = service._keys_cache.get("994a84bf-02b8-4a52-ad55-35b733d377bb")
    assert key is not None
