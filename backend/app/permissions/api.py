"""Authenticated account-control and authorization-decision endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter

from backend.app.auth.dependencies import CurrentIdentity
from backend.app.permissions.dependencies import (
    PermissionAdministrationDependency,
    PermissionsEngineDependency,
)
from backend.app.permissions.schemas import (
    AuthorizationDecision,
    AuthorizationRequest,
    ConfirmationResponse,
    PermissionGrantRequest,
    PermissionResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/authorization/evaluate", response_model=AuthorizationDecision)
async def evaluate_authorization(
    proposal: AuthorizationRequest,
    identity: CurrentIdentity,
    engine: PermissionsEngineDependency,
) -> AuthorizationDecision:
    """Evaluate a proposal without invoking an executor or external integration."""
    return await engine.authorize(identity, proposal)


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(
    identity: CurrentIdentity,
    service: PermissionAdministrationDependency,
) -> list[PermissionResponse]:
    rows = await service.list_owned(identity)
    return [
        PermissionResponse.from_models(permission, capability) for permission, capability in rows
    ]


@router.get("/permissions/{permission_id}", response_model=PermissionResponse)
async def get_permission(
    permission_id: UUID,
    identity: CurrentIdentity,
    service: PermissionAdministrationDependency,
) -> PermissionResponse:
    permission, capability = await service.get_owned(identity, permission_id)
    return PermissionResponse.from_models(permission, capability)


@router.post("/permissions/grant", response_model=PermissionResponse)
async def grant_permission(
    grant: PermissionGrantRequest,
    identity: CurrentIdentity,
    service: PermissionAdministrationDependency,
) -> PermissionResponse:
    permission, capability = await service.grant(identity, grant)
    logger.info(
        "Permission granted or resolved idempotently",
        extra={
            "user_id": str(identity.user_id),
            "device_id": str(identity.device_id) if identity.device_id else None,
            "capability_key": capability.key,
        },
    )
    return PermissionResponse.from_models(permission, capability)


@router.post("/permissions/{permission_id}/revoke", response_model=PermissionResponse)
async def revoke_permission(
    permission_id: UUID,
    identity: CurrentIdentity,
    service: PermissionAdministrationDependency,
) -> PermissionResponse:
    permission, capability = await service.revoke(identity, permission_id)
    logger.info(
        "Permission revoked",
        extra={
            "user_id": str(identity.user_id),
            "device_id": str(identity.device_id) if identity.device_id else None,
            "capability_key": capability.key,
        },
    )
    return PermissionResponse.from_models(permission, capability)


@router.post(
    "/confirmations/{confirmation_id}/approve",
    response_model=ConfirmationResponse,
)
async def approve_confirmation(
    confirmation_id: UUID,
    identity: CurrentIdentity,
    service: PermissionAdministrationDependency,
) -> ConfirmationResponse:
    confirmation = await service.approve_confirmation(identity, confirmation_id)
    return ConfirmationResponse.from_model(confirmation)


@router.post(
    "/confirmations/{confirmation_id}/reject",
    response_model=ConfirmationResponse,
)
async def reject_confirmation(
    confirmation_id: UUID,
    identity: CurrentIdentity,
    service: PermissionAdministrationDependency,
) -> ConfirmationResponse:
    confirmation = await service.reject_confirmation(identity, confirmation_id)
    return ConfirmationResponse.from_model(confirmation)
