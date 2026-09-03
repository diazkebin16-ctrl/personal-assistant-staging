"""Validated authority requests and controlled API responses."""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from backend.app.core.redaction import is_sensitive_key
from backend.app.core.time import as_utc
from backend.app.permissions.enums import (
    AuthorizationDecisionType,
    ConfirmationPolicy,
    ConfirmationStatus,
    DecisionReason,
    PermissionGrantSource,
    PermissionStatus,
    RiskLevel,
)
from backend.app.permissions.models import Capability, ConfirmationRequest, Permission

CapabilityKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$",
    ),
]
ActionName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    ),
]
ResourceType = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    ),
]
ResourceId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
ReasonText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]

_CONTEXT_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_CONTEXT_ENTRIES = 32
_MAX_CONTEXT_BYTES = 4096


class PermissionScope(BaseModel):
    """Small structured scope language: resource type, IDs, and operations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_type: ResourceType
    resource_ids: list[ResourceId] = Field(default_factory=list, max_length=32)
    operations: list[ActionName] = Field(min_length=1, max_length=32)

    @field_validator("resource_ids", "operations")
    @classmethod
    def normalize_unique_values(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Scope entries must be unique")
        return sorted(value)

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"), separators=(",", ":"), sort_keys=True
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def authorizes(self, requested: "PermissionScope") -> bool:
        if self.resource_type != requested.resource_type:
            return False
        if not set(requested.operations).issubset(self.operations):
            return False
        if not requested.resource_ids:
            return not self.resource_ids
        return bool(self.resource_ids) and set(requested.resource_ids).issubset(self.resource_ids)


class ResourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_type: ResourceType
    resource_id: ResourceId | None = None


class AuthorizationRequest(BaseModel):
    """Untrusted proposal data; authenticated identity is injected separately."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_key: CapabilityKey
    action: ActionName
    scope: PermissionScope
    resource: ResourceReference | None = None
    context: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    confirmation_id: UUID | None = None

    @field_validator("context")
    @classmethod
    def validate_context(
        cls, value: dict[str, str | int | float | bool | None]
    ) -> dict[str, str | int | float | bool | None]:
        if len(value) > _MAX_CONTEXT_ENTRIES:
            raise ValueError("Too many context entries")
        if any(_CONTEXT_KEY.fullmatch(key) is None or is_sensitive_key(key) for key in value):
            raise ValueError("Invalid or sensitive context key")
        encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
        if len(encoded) > _MAX_CONTEXT_BYTES:
            raise ValueError("Context is too large")
        return value

    @model_validator(mode="after")
    def validate_action_and_resource(self) -> "AuthorizationRequest":
        if self.action not in self.scope.operations:
            raise ValueError("Action must be present in requested scope operations")
        if self.resource is not None:
            if self.resource.resource_type != self.scope.resource_type:
                raise ValueError("Resource type must match the requested scope")
            if (
                self.resource.resource_id is not None
                and self.resource.resource_id not in self.scope.resource_ids
            ):
                raise ValueError("Resource ID must be present in the requested scope")
        return self


class RiskAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    risk_level: RiskLevel
    reversible: bool
    financial: bool
    external_side_effect: bool
    data_destructive: bool
    privacy_impact: bool
    reasons: tuple[str, ...]


class AuthorizationDecision(BaseModel):
    """Immutable result from the authority pipeline; it does not execute anything."""

    model_config = ConfigDict(frozen=True)

    decision_id: UUID
    decision: AuthorizationDecisionType
    reason_codes: tuple[DecisionReason, ...]
    permission_id: UUID | None
    risk_level: RiskLevel
    confirmation_required: bool
    confirmation_id: UUID | None
    scope_match: bool
    financial_guard_triggered: bool
    created_at: datetime


class PermissionGrantRequest(BaseModel):
    """AAL2 account-control input with no owner or grant-source authority fields."""

    model_config = ConfigDict(extra="forbid")

    capability_key: CapabilityKey
    scope: PermissionScope
    device_id: UUID | None = None
    confirmation_policy: ConfirmationPolicy
    auto_execute: bool = False
    expires_at: datetime | None = None
    reason: ReasonText | None = None

    @field_validator("expires_at")
    @classmethod
    def normalize_expiry(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Permission expiry must be timezone-aware")
        return value.astimezone(UTC)


class CapabilityResponse(BaseModel):
    key: str
    name: str
    description: str
    category: str
    default_risk_level: RiskLevel
    allowed_actions: list[ActionName] = Field(min_length=1, max_length=32)
    external_side_effect: bool
    financial: bool
    data_destructive: bool
    privacy_impact: bool
    enabled: bool

    @classmethod
    def from_model(cls, capability: Capability) -> "CapabilityResponse":
        return cls(
            key=capability.key,
            name=capability.name,
            description=capability.description,
            category=capability.category,
            default_risk_level=RiskLevel(capability.default_risk_level),
            allowed_actions=capability.allowed_actions,
            external_side_effect=capability.external_side_effect,
            financial=capability.financial,
            data_destructive=capability.data_destructive,
            privacy_impact=capability.privacy_impact,
            enabled=capability.enabled,
        )


class PermissionResponse(BaseModel):
    id: UUID
    capability: CapabilityResponse
    scope: PermissionScope
    device_id: UUID | None
    status: PermissionStatus
    confirmation_policy: ConfirmationPolicy
    auto_execute: bool
    grant_source: PermissionGrantSource
    granted_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    reason: str | None
    last_relevant_use_at: datetime | None

    @classmethod
    def from_models(cls, permission: Permission, capability: Capability) -> "PermissionResponse":
        return cls(
            id=permission.id,
            capability=CapabilityResponse.from_model(capability),
            scope=PermissionScope.model_validate(permission.scope),
            device_id=permission.device_id,
            status=permission.status,
            confirmation_policy=permission.confirmation_policy,
            auto_execute=permission.auto_execute,
            grant_source=permission.grant_source,
            granted_at=as_utc(permission.granted_at),
            expires_at=as_utc(permission.expires_at) if permission.expires_at else None,
            revoked_at=as_utc(permission.revoked_at) if permission.revoked_at else None,
            reason=permission.reason,
            last_relevant_use_at=(
                as_utc(permission.last_used_at) if permission.last_used_at else None
            ),
        )


class ConfirmationResponse(BaseModel):
    id: UUID
    authorization_decision_id: UUID
    capability_key: str
    action: str
    status: ConfirmationStatus
    requested_at: datetime
    expires_at: datetime
    confirmed_at: datetime | None
    rejected_at: datetime | None
    consumed_at: datetime | None

    @classmethod
    def from_model(cls, confirmation: ConfirmationRequest) -> "ConfirmationResponse":
        return cls(
            id=confirmation.id,
            authorization_decision_id=confirmation.authorization_decision_id,
            capability_key=confirmation.capability_key,
            action=confirmation.action,
            status=confirmation.status,
            requested_at=as_utc(confirmation.requested_at),
            expires_at=as_utc(confirmation.expires_at),
            confirmed_at=(as_utc(confirmation.confirmed_at) if confirmation.confirmed_at else None),
            rejected_at=as_utc(confirmation.rejected_at) if confirmation.rejected_at else None,
            consumed_at=as_utc(confirmation.consumed_at) if confirmation.consumed_at else None,
        )
