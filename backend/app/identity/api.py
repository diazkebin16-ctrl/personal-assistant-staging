"""Versioned identity and owned-device API endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter

from backend.app.auth.dependencies import CurrentIdentity
from backend.app.identity.dependencies import IdentityServiceDependency
from backend.app.identity.schemas import DeviceRegistrationRequest, DeviceResponse, MeResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/me", response_model=MeResponse)
async def current_identity(identity: CurrentIdentity) -> MeResponse:
    return MeResponse.from_identity(identity)


@router.post("/devices/register", response_model=DeviceResponse)
async def register_device(
    registration: DeviceRegistrationRequest,
    identity: CurrentIdentity,
    service: IdentityServiceDependency,
) -> DeviceResponse:
    device = await service.register_device(identity, registration)
    logger.info(
        "Device registered or refreshed",
        extra={"user_id": str(identity.user_id), "device_id": str(device.id)},
    )
    return DeviceResponse.from_device(device)


@router.get("/devices", response_model=list[DeviceResponse])
async def list_devices(
    identity: CurrentIdentity,
    service: IdentityServiceDependency,
) -> list[DeviceResponse]:
    devices = await service.list_devices(identity)
    return [DeviceResponse.from_device(device) for device in devices]


@router.post("/devices/{device_id}/revoke", response_model=DeviceResponse)
async def revoke_device(
    device_id: UUID,
    identity: CurrentIdentity,
    service: IdentityServiceDependency,
) -> DeviceResponse:
    device = await service.revoke_device(identity, device_id)
    logger.info(
        "Device revoked",
        extra={"user_id": str(identity.user_id), "device_id": str(device.id)},
    )
    return DeviceResponse.from_device(device)
