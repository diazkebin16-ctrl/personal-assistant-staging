"""FastAPI dependency that creates a verified request identity context."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.auth.claims import SupabaseClaims
from backend.app.auth.jwt import TokenVerifier, get_token_verifier
from backend.app.core.errors import AuthenticationRequiredError, DeviceNotFoundError
from backend.app.identity.context import IdentityContext
from backend.app.identity.dependencies import IdentityServiceDependency

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)

BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]
VerifierDependency = Annotated[TokenVerifier, Depends(get_token_verifier)]


def require_bearer_credentials(credentials: BearerCredentials) -> HTTPAuthorizationCredentials:
    """Stop unauthenticated requests before JWKS or database dependencies resolve."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationRequiredError
    return credentials


RequiredBearer = Annotated[
    HTTPAuthorizationCredentials,
    Depends(require_bearer_credentials),
]


def get_verified_claims(
    credentials: RequiredBearer,
    verifier: VerifierDependency,
) -> SupabaseClaims:
    """Verify the token before identity persistence is made available."""
    return verifier.verify(credentials.credentials)


VerifiedClaims = Annotated[SupabaseClaims, Depends(get_verified_claims)]


async def get_current_identity(
    claims: VerifiedClaims,
    service: IdentityServiceDependency,
    raw_device_id: Annotated[str | None, Header(alias="X-Device-ID")] = None,
) -> IdentityContext:
    """Verify the bearer token and resolve its internal user/session/device mapping."""
    requested_device_id: UUID | None = None
    if raw_device_id is not None:
        try:
            requested_device_id = UUID(raw_device_id)
        except ValueError:
            raise DeviceNotFoundError from None

    identity = await service.resolve_identity(claims, requested_device_id)
    logger.info(
        "Authenticated identity resolved",
        extra={
            "user_id": str(identity.user_id),
            "device_id": str(identity.device_id) if identity.device_id else None,
        },
    )
    return identity


CurrentIdentity = Annotated[IdentityContext, Depends(get_current_identity)]
