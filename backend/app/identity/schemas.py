"""Controlled API input and output schemas for identity devices."""

import json
import re
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from backend.app.core.time import as_utc
from backend.app.identity.context import IdentityContext
from backend.app.identity.models import Device, DeviceType

DeviceName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
DeviceIdentifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
PlatformName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
PublicKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4096)]

_CAPABILITY_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_CAPABILITIES = 32
_MAX_CAPABILITIES_BYTES = 4096


class DeviceRegistrationRequest(BaseModel):
    """Client-supplied device metadata with no ownership fields."""

    model_config = ConfigDict(extra="forbid")

    device_name: DeviceName
    device_type: DeviceType
    platform: PlatformName
    device_identifier: DeviceIdentifier
    capabilities: dict[str, bool] = Field(default_factory=dict)
    public_key: PublicKey | None = None

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: dict[str, bool]) -> dict[str, bool]:
        if len(value) > _MAX_CAPABILITIES:
            raise ValueError("Too many capability entries")
        if any(_CAPABILITY_NAME.fullmatch(name) is None for name in value):
            raise ValueError("Invalid capability name")
        encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
        if len(encoded) > _MAX_CAPABILITIES_BYTES:
            raise ValueError("Capability manifest is too large")
        return value

    @field_validator("public_key")
    @classmethod
    def reject_private_keys(cls, value: str | None) -> str | None:
        if value is not None and "PRIVATE KEY" in value.upper():
            raise ValueError("Private keys are not accepted")
        return value


class DeviceResponse(BaseModel):
    """Safe device representation; public-key material is not echoed."""

    id: UUID
    device_name: str
    device_type: DeviceType
    platform: str
    trusted: bool
    capabilities: dict[str, bool]
    has_public_key: bool
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None

    @classmethod
    def from_device(cls, device: Device) -> "DeviceResponse":
        return cls(
            id=device.id,
            device_name=device.device_name,
            device_type=device.device_type,
            platform=device.platform,
            trusted=device.trusted,
            capabilities=device.capabilities,
            has_public_key=device.public_key is not None,
            created_at=as_utc(device.created_at),
            updated_at=as_utc(device.updated_at),
            last_seen_at=as_utc(device.last_seen_at),
            revoked_at=as_utc(device.revoked_at) if device.revoked_at else None,
        )


class MeResponse(BaseModel):
    """Minimal safe current-identity response."""

    user_id: UUID
    auth_user_id: UUID
    display_name: str | None
    device_id: UUID | None
    authenticated: bool
    authentication_level: str

    @classmethod
    def from_identity(cls, identity: IdentityContext) -> "MeResponse":
        return cls(
            user_id=identity.user_id,
            auth_user_id=identity.auth_user_id,
            display_name=identity.display_name,
            device_id=identity.device_id,
            authenticated=identity.authenticated,
            authentication_level=identity.authentication_level.value,
        )


def safe_display_name(metadata: dict[str, Any]) -> str | None:
    """Extract non-authoritative display metadata with strict bounds."""
    for key in ("display_name", "full_name", "name"):
        candidate = metadata.get(key)
        if isinstance(candidate, str):
            normalized = " ".join(candidate.split())
            if 1 <= len(normalized) <= 100:
                return normalized
    return None
