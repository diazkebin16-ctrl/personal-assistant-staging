"""Cryptographic Supabase JWT validation tests."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWK
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from backend.app.auth.jwt import SupabaseJwtVerifier
from backend.app.core.errors import (
    AuthVerificationUnavailableError,
    ExpiredTokenError,
    InvalidTokenError,
)

ISSUER = "https://test.supabase.co/auth/v1"
AUDIENCE = "authenticated"
KEY_ID = "phase1-test-key"


class StaticJwksClient:
    def __init__(self, signing_key: PyJWK) -> None:
        self.signing_key = signing_key
        self.calls = 0

    def get_signing_key(self, kid: str) -> PyJWK:
        self.calls += 1
        if kid != self.signing_key.key_id:
            raise PyJWKClientError("No matching key")
        return self.signing_key


class FailingJwksClient:
    def get_signing_key(self, _: str) -> PyJWK:
        raise PyJWKClientConnectionError("JWKS unavailable")


def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def public_jwk(key: rsa.RSAPrivateKey) -> PyJWK:
    data = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    data.update({"kid": KEY_ID, "alg": "RS256", "use": "sig"})
    return PyJWK.from_dict(data)


def payload(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(uuid4()),
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": int((now + timedelta(minutes=10)).timestamp()),
        "iat": int(now.timestamp()),
        "role": "authenticated",
        "session_id": str(uuid4()),
        "aal": "aal1",
    }
    claims.update(overrides)
    return claims


def encode(key: rsa.RSAPrivateKey, claims: dict[str, Any]) -> str:
    return jwt.encode(
        claims,
        key,
        algorithm="RS256",
        headers={"kid": KEY_ID, "typ": "JWT"},
    )


def verifier(key: rsa.RSAPrivateKey) -> tuple[SupabaseJwtVerifier, StaticJwksClient]:
    client = StaticJwksClient(public_jwk(key))
    instance = SupabaseJwtVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url="https://unused.invalid/jwks.json",
        cache_ttl=600,
        timeout_seconds=5,
        jwks_client=client,
    )
    return instance, client


def test_valid_token_is_verified_cryptographically() -> None:
    key = private_key()
    instance, client = verifier(key)

    claims = instance.verify(encode(key, payload()))

    assert claims.role == "authenticated"
    assert claims.authentication_level.value == "AAL1"
    assert client.calls == 1


def test_mfa_assurance_is_mapped_without_promoting_unknown_values() -> None:
    key = private_key()
    instance, _ = verifier(key)

    aal2 = instance.verify(encode(key, payload(aal="aal2")))
    unknown = instance.verify(encode(key, payload(aal="future-aal")))

    assert aal2.authentication_level.value == "AAL2"
    assert unknown.authentication_level.value == "UNKNOWN"


def test_expired_token_is_rejected() -> None:
    key = private_key()
    instance, _ = verifier(key)
    expired = int((datetime.now(UTC) - timedelta(seconds=1)).timestamp())

    with pytest.raises(ExpiredTokenError):
        instance.verify(encode(key, payload(exp=expired)))


def test_invalid_signature_is_rejected() -> None:
    trusted_key = private_key()
    attacker_key = private_key()
    instance, _ = verifier(trusted_key)

    with pytest.raises(InvalidTokenError):
        instance.verify(encode(attacker_key, payload()))


def test_wrong_issuer_is_rejected() -> None:
    key = private_key()
    instance, _ = verifier(key)

    with pytest.raises(InvalidTokenError):
        instance.verify(encode(key, payload(iss="https://attacker.invalid/auth/v1")))


def test_wrong_audience_is_rejected() -> None:
    key = private_key()
    instance, _ = verifier(key)

    with pytest.raises(InvalidTokenError):
        instance.verify(encode(key, payload(aud="wrong-audience")))


def test_unsupported_algorithm_is_rejected_before_jwks_lookup() -> None:
    key = private_key()
    instance, client = verifier(key)
    encoded_jwt = jwt.encode(
        payload(),
        "test-only-shared-secret-that-is-long-enough",
        algorithm="HS256",
        headers={"kid": KEY_ID, "typ": "JWT"},
    )

    with pytest.raises(InvalidTokenError):
        instance.verify(encoded_jwt)

    assert client.calls == 0


def test_malformed_jwt_is_rejected() -> None:
    key = private_key()
    instance, _ = verifier(key)

    with pytest.raises(InvalidTokenError):
        instance.verify("not-a-jwt")


def test_missing_required_claim_is_rejected() -> None:
    key = private_key()
    instance, _ = verifier(key)
    claims = payload()
    del claims["sub"]

    with pytest.raises(InvalidTokenError):
        instance.verify(encode(key, claims))


def test_non_user_role_is_rejected() -> None:
    key = private_key()
    instance, _ = verifier(key)

    with pytest.raises(InvalidTokenError):
        instance.verify(encode(key, payload(role="service_role")))


def test_jwks_connection_failure_rejects_safely() -> None:
    key = private_key()
    instance = SupabaseJwtVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url="https://unused.invalid/jwks.json",
        cache_ttl=600,
        timeout_seconds=5,
        jwks_client=FailingJwksClient(),
    )

    with pytest.raises(AuthVerificationUnavailableError):
        instance.verify(encode(key, payload()))
