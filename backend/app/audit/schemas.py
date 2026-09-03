"""Controlled audit command and response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.audit.models import AuditEvent
from backend.app.core.time import as_utc
from backend.app.permissions.enums import ActorType, AuditEventType, AuditResult, RiskLevel


class AuditRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    device_id: UUID | None = None
    session_id: UUID | None = None
    actor_type: ActorType
    event_type: AuditEventType
    result: AuditResult
    capability_key: str | None = None
    action: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    risk_level: RiskLevel | None = None
    permission_id: UUID | None = None
    authorization_decision_id: UUID | None = None
    confirmation_id: UUID | None = None
    reason_codes: tuple[str, ...] = ()
    trace_id: str | None = None
    task_id: UUID | None = None
    execution_id: UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class AuditEventResponse(BaseModel):
    id: UUID
    timestamp: datetime
    actor_type: ActorType
    event_type: AuditEventType
    capability_key: str | None
    action: str | None
    resource_type: str | None
    resource_id: str | None
    risk_level: RiskLevel | None
    permission_id: UUID | None
    authorization_decision_id: UUID | None
    confirmation_id: UUID | None
    result: AuditResult
    reason_codes: list[str]
    trace_id: str | None
    task_id: UUID | None
    execution_id: UUID | None
    metadata: dict[str, object]

    @classmethod
    def from_model(cls, event: AuditEvent) -> "AuditEventResponse":
        return cls(
            id=event.id,
            timestamp=as_utc(event.timestamp),
            actor_type=event.actor_type,
            event_type=event.event_type,
            capability_key=event.capability_key,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            risk_level=RiskLevel(event.risk_level) if event.risk_level is not None else None,
            permission_id=event.permission_id,
            authorization_decision_id=event.authorization_decision_id,
            confirmation_id=event.confirmation_id,
            result=event.result,
            reason_codes=event.reason_codes,
            trace_id=event.trace_id,
            task_id=event.task_id,
            execution_id=event.execution_id,
            metadata=event.metadata_payload,
        )
