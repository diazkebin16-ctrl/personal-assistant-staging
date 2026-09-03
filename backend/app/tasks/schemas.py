"""Validated Task Engine commands and controlled responses."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from backend.app.core.metadata import sanitize_metadata
from backend.app.core.time import as_utc
from backend.app.permissions.schemas import ActionName, CapabilityKey, PermissionScope
from backend.app.tasks.enums import (
    TaskActorType,
    TaskAttemptStatus,
    TaskEventType,
    TaskPriority,
    TaskStatus,
)
from backend.app.tasks.models import Task, TaskAttempt, TaskEvent

IdempotencyKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
SafeCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128, pattern=r"^[A-Z0-9_]+$"),
]
SafeMessage = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
WorkerId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    ),
]

MAX_TASK_METADATA_BYTES = 4096


def _bounded_metadata(value: dict[str, object]) -> dict[str, object]:
    return sanitize_metadata(value, max_bytes=MAX_TASK_METADATA_BYTES)


class TaskCreateRequest(BaseModel):
    """Untrusted client proposal; identity, state, and authorization are server-owned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_key: CapabilityKey
    action: ActionName
    scope: PermissionScope
    idempotency_key: IdempotencyKey
    device_id: UUID | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    expires_at: datetime | None = None
    max_retries: int = Field(default=0, ge=0, le=10)
    parent_task_id: UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("expires_at")
    @classmethod
    def normalize_expiry(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Task expiry must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, object]) -> dict[str, object]:
        return _bounded_metadata(value)

    @property
    def fingerprint(self) -> str:
        normalized = {
            "action": self.action,
            "capability_key": self.capability_key,
            "device_id": str(self.device_id) if self.device_id else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "max_retries": self.max_retries,
            "metadata": self.metadata,
            "parent_task_id": str(self.parent_task_id) if self.parent_task_id else None,
            "priority": self.priority.value,
            "scope": self.scope.model_dump(mode="json"),
        }
        encoded = json.dumps(normalized, separators=(",", ":"), sort_keys=True).encode()
        return hashlib.sha256(encoded).hexdigest()


class TaskCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)


class TaskClaimRequest(BaseModel):
    """Internal-only worker claim command; never accepted by a public route."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)
    worker_id: WorkerId
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, object]) -> dict[str, object]:
        return _bounded_metadata(value)


class TaskCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)
    result_metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("result_metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, object]) -> dict[str, object]:
        return _bounded_metadata(value)


class TaskFailureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)
    error_code: SafeCode
    safe_error_message: SafeMessage
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, object]) -> dict[str, object]:
        return _bounded_metadata(value)


class TaskEventResponse(BaseModel):
    id: UUID
    event_type: TaskEventType
    from_state: TaskStatus | None
    to_state: TaskStatus
    timestamp: datetime
    reason_code: str
    actor_type: TaskActorType
    actor_id: str | None
    metadata: dict[str, object]

    @classmethod
    def from_model(cls, event: TaskEvent) -> "TaskEventResponse":
        return cls(
            id=event.id,
            event_type=event.event_type,
            from_state=event.from_state,
            to_state=event.to_state,
            timestamp=as_utc(event.timestamp),
            reason_code=event.reason_code,
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            metadata=event.metadata_payload,
        )


class TaskAttemptResponse(BaseModel):
    id: UUID
    attempt_number: int
    status: TaskAttemptStatus
    started_at: datetime
    finished_at: datetime | None
    error_code: str | None
    safe_error_message: str | None
    worker_id: str
    execution_id: UUID
    metadata: dict[str, object]

    @classmethod
    def from_model(cls, attempt: TaskAttempt) -> "TaskAttemptResponse":
        return cls(
            id=attempt.id,
            attempt_number=attempt.attempt_number,
            status=attempt.status,
            started_at=as_utc(attempt.started_at),
            finished_at=as_utc(attempt.finished_at) if attempt.finished_at else None,
            error_code=attempt.error_code,
            safe_error_message=attempt.safe_error_message,
            worker_id=attempt.worker_id,
            execution_id=attempt.execution_id,
            metadata=attempt.metadata_payload,
        )


class TaskResponse(BaseModel):
    id: UUID
    device_id: UUID | None
    capability_key: str
    action: str
    scope: PermissionScope
    status: TaskStatus
    priority: TaskPriority
    idempotency_key: str
    authorization_decision_id: UUID
    confirmation_request_id: UUID | None
    parent_task_id: UUID | None
    created_at: datetime
    updated_at: datetime
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    expires_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    retry_count: int
    max_retries: int
    next_retry_at: datetime | None
    version: int
    metadata: dict[str, object]
    result_metadata: dict[str, object]

    @classmethod
    def from_model(cls, task: Task) -> "TaskResponse":
        return cls(
            id=task.id,
            device_id=task.device_id,
            capability_key=task.capability_key,
            action=task.action,
            scope=PermissionScope.model_validate(task.scope),
            status=task.status,
            priority=task.priority,
            idempotency_key=task.idempotency_key,
            authorization_decision_id=task.authorization_decision_id,
            confirmation_request_id=task.confirmation_request_id,
            parent_task_id=task.parent_task_id,
            created_at=as_utc(task.created_at),
            updated_at=as_utc(task.updated_at),
            queued_at=as_utc(task.queued_at) if task.queued_at else None,
            started_at=as_utc(task.started_at) if task.started_at else None,
            completed_at=as_utc(task.completed_at) if task.completed_at else None,
            cancelled_at=as_utc(task.cancelled_at) if task.cancelled_at else None,
            expires_at=as_utc(task.expires_at) if task.expires_at else None,
            last_error_code=task.last_error_code,
            last_error_message=task.last_error_message,
            retry_count=task.retry_count,
            max_retries=task.max_retries,
            next_retry_at=as_utc(task.next_retry_at) if task.next_retry_at else None,
            version=task.version,
            metadata=task.metadata_payload,
            result_metadata=task.result_metadata,
        )


class TaskDetailResponse(TaskResponse):
    attempts: list[TaskAttemptResponse]
    events: list[TaskEventResponse]
