"""Strict asymmetric Supabase JWT verification with cached JWKS discovery."""

from functools import lru_cache
from typing import Any, Protocol

import jwt
from jwt import PyJWK, PyJWKClient
from jwt.exceptions import (
    ExpiredSignatureError,
    PyJWKClientConnectionError,
    PyJWKClientError,
)
from jwt.exceptions import (
    InvalidTokenError as PyJwtInvalidTokenError,
)
from pydantic import ValidationError

from backend.app.auth.claims import SupabaseClaims
from backend.app.core.config import get_settings
from backend.app.core.errors import (
    AuthVerificationUnavailableError,
    ExpiredTokenError,
    InvalidTokenError,
)

ALLOWED_JWT_ALGORITHMS = ("ES256", "RS256")
MAX_TOKEN_LENGTH = 8192


class TokenVerifier(Protocol):
    """Narrow contract used by request authentication and test fakes."""

    def verify(self, token: str) -> SupabaseClaims: ...


class JwksClient(Protocol):
    """Subset of PyJWKClient needed by the verifier."""

    def get_signing_key(self, kid: str) -> PyJWK: ...


class SupabaseJwtVerifier:
    """Verify Supabase access tokens without creating a parallel auth system."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_url: str,
        cache_ttl: int,
        timeout_seconds: float,
        jwks_client: JwksClient | None = None,
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.jwks_client = jwks_client or PyJWKClient(
            jwks_url,
            cache_keys=False,
            cache_jwk_set=True,
            lifespan=cache_ttl,
            timeout=timeout_seconds,
        )

    def verify(self, token: str) -> SupabaseClaims:
        """Verify format, algorithm, signature, issuer, audience, expiry, and claims."""
        if not token or len(token) > MAX_TOKEN_LENGTH or len(token.split(".")) != 3:
            raise InvalidTokenError

        try:
            header: dict[str, Any] = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            key_id = header.get("kid")

            if algorithm not in ALLOWED_JWT_ALGORITHMS:
                raise InvalidTokenError
            if header.get("typ") != "JWT":
                raise InvalidTokenError
            if not isinstance(key_id, str) or not key_id:
                raise InvalidTokenError

            signing_key = self.jwks_client.get_signing_key(key_id)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(ALLOWED_JWT_ALGORITHMS),
                audience=self.audience,
                issuer=self.issuer,
                options={
                    "require": ["exp", "iss", "aud", "sub", "role"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
            return SupabaseClaims.model_validate(payload)
        except ExpiredSignatureError:
            raise ExpiredTokenError from None
        except PyJWKClientConnectionError:
            raise AuthVerificationUnavailableError from None
        except InvalidTokenError:
            raise
        except (PyJWKClientError, PyJwtInvalidTokenError, ValidationError, TypeError, ValueError):
            raise InvalidTokenError from None


@lru_cache(maxsize=1)
def get_token_verifier() -> TokenVerifier:
    """Build a verifier only when an authenticated endpoint is requested."""
    settings = get_settings()
    issuer = settings.effective_jwt_issuer
    jwks_url = settings.effective_jwks_url
    if issuer is None or jwks_url is None:
        raise AuthVerificationUnavailableError

    return SupabaseJwtVerifier(
        issuer=issuer,
        audience=settings.supabase_jwt_audience,
        jwks_url=jwks_url,
        cache_ttl=settings.auth_jwks_cache_ttl,
        timeout_seconds=settings.auth_jwks_timeout_seconds,
    )
