"""Strict Orchestrator commands, untrusted AI proposals, and immutable handoff evidence."""

import hashlib
import json
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

from backend.app.core.metadata import sanitize_metadata
from backend.app.core.time import as_utc
from backend.app.orchestrator.enums import (
    IntentCategory,
    OrchestrationState,
    SafeMode,
    SideEffectClass,
)
from backend.app.orchestrator.models import OrchestrationWorkflow
from backend.app.permissions.enums import RiskLevel
from backend.app.permissions.schemas import ActionName, CapabilityKey, PermissionScope
from backend.app.security.classification import DataSensitivity
from backend.app.tasks.schemas import IdempotencyKey

IntentLabel = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9._-]*$"
    ),
]
PlanSummary = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
MAX_ORCHESTRATION_INPUT = 50_000
MAX_ARGUMENT_BYTES = 8192


class IntentMetadata(BaseModel):
    """Non-authoritative request category; it carries no risk or permission claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: IntentCategory
    label: IntentLabel


class OrchestrationRequest(BaseModel):
    """Narrow public command without owner, provider, model, risk, or confirmation authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: IntentMetadata
    input_text: str = Field(min_length=1, max_length=MAX_ORCHESTRATION_INPUT, repr=False)
    idempotency_key: IdempotencyKey
    use_memory_context: bool = True
    memory_items_per_category: int = Field(default=3, ge=1, le=5)
    requested_output_tokens: int = Field(default=1024, ge=1, le=8192)
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def normalize_expiry(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Orchestration expiry must be timezone-aware")
        return value.astimezone(UTC)

    @property
    def fingerprint(self) -> str:
        normalized = {
            "input_sha256": hashlib.sha256(self.input_text.encode()).hexdigest(),
            "intent": self.intent.model_dump(mode="json"),
            "memory_items_per_category": self.memory_items_per_category,
            "requested_output_tokens": self.requested_output_tokens,
            "use_memory_context": self.use_memory_context,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
        encoded = json.dumps(normalized, separators=(",", ":"), sort_keys=True).encode()
        return hashlib.sha256(encoded).hexdigest()


class CandidateAction(BaseModel):
    """Untrusted model proposal; arguments remain inert data and never executable code."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_key: CapabilityKey
    action: ActionName
    scope: PermissionScope
    arguments: dict[str, object] = Field(default_factory=dict)
    side_effect_class: SideEffectClass

    @field_validator("arguments")
    @classmethod
    def validate_arguments(cls, value: dict[str, object]) -> dict[str, object]:
        return sanitize_metadata(value, max_bytes=MAX_ARGUMENT_BYTES)

    @model_validator(mode="after")
    def action_is_scoped(self) -> "CandidateAction":
        if self.action not in self.scope.operations:
            raise ValueError("Candidate action must be present in its scope")
        return self


class CandidatePlan(BaseModel):
    """Validated proposal. Phase 6 permits at most one actionable handoff per workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: PlanSummary
    actions: tuple[CandidateAction, ...] = Field(default=(), max_length=1)

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"), separators=(",", ":"), sort_keys=True
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


class AuthorizationEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: UUID
    permission_id: UUID | None
    risk_level: RiskLevel
    confirmation_id: UUID | None
    financial_guard_triggered: bool


class AuthorizedActionEnvelope(BaseModel):
    """Immutable evidence for a future executor that must independently revalidate it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    workflow_id: UUID
    task_id: UUID
    user_id: UUID
    device_id: UUID | None
    capability_key: CapabilityKey
    action: ActionName
    arguments: dict[str, object]
    scope_digest: str = Field(min_length=64, max_length=64)
    plan_fingerprint: str = Field(min_length=64, max_length=64)
    authorization: AuthorizationEvaluation
    safe_mode: SafeMode
    policy_version: str = Field(min_length=1, max_length=64)
    idempotency_key: IdempotencyKey
    expires_at: datetime | None


class OrchestrationContext(BaseModel):
    """Ephemeral coordination metadata; raw memory and prompts are never persisted here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    effective_sensitivity: DataSensitivity
    memory_item_count: int = Field(ge=0, le=20)
    estimated_input_tokens: int = Field(ge=0, le=2_000_000)


class OrchestrationResponse(BaseModel):
    id: UUID
    device_id: UUID | None
    intent_category: IntentCategory
    state: OrchestrationState
    safe_mode: SafeMode
    task_id: UUID | None
    routing_decision_id: UUID | None
    authorization_decision_id: UUID | None
    confirmation_request_id: UUID | None
    plan_fingerprint: str | None
    failure_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None

    @classmethod
    def from_model(cls, workflow: OrchestrationWorkflow) -> "OrchestrationResponse":
        return cls(
            id=workflow.id,
            device_id=workflow.device_id,
            intent_category=workflow.intent_category,
            state=workflow.state,
            safe_mode=workflow.safe_mode,
            task_id=workflow.task_id,
            routing_decision_id=workflow.routing_decision_id,
            authorization_decision_id=workflow.authorization_decision_id,
            confirmation_request_id=workflow.confirmation_request_id,
            plan_fingerprint=workflow.plan_fingerprint,
            failure_reason=workflow.failure_reason,
            version=workflow.version,
            created_at=as_utc(workflow.created_at),
            updated_at=as_utc(workflow.updated_at),
            expires_at=as_utc(workflow.expires_at) if workflow.expires_at else None,
        )


class OrchestrationResult(BaseModel):
    """Public-safe result; answer is ephemeral and never persisted by the Orchestrator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow: OrchestrationResponse
    answer: str | None = Field(default=None, max_length=1_000_000, repr=False)
    envelope_created: bool = False


class OrchestrationMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)
