"""Transactional Task Engine service with default-deny authorization linkage."""

import logging
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.audit.engine import AuditEngine
from backend.app.audit.schemas import AuditRecord
from backend.app.core.errors import (
    InvalidTaskTransitionError,
    TaskAlreadyTerminalError,
    TaskConcurrentModificationError,
    TaskDeviceInvalidError,
    TaskIdempotencyConflictError,
    TaskNotClaimableError,
    TaskNotFoundError,
)
from backend.app.core.metadata import sanitize_metadata
from backend.app.core.time import at_or_after
from backend.app.identity.context import IdentityContext
from backend.app.identity.models import Device, utc_now
from backend.app.permissions.engine import PermissionsEngine
from backend.app.permissions.enums import (
    ActorType,
    AuditEventType,
    AuditResult,
    AuthorizationDecisionType,
    DecisionReason,
)
from backend.app.permissions.schemas import (
    AuthorizationDecision,
    AuthorizationRequest,
    PermissionScope,
)
from backend.app.tasks.enums import (
    TaskActorType,
    TaskAttemptStatus,
    TaskEventType,
    TaskStatus,
    TaskTransitionReason,
)
from backend.app.tasks.models import Task, TaskAttempt, TaskEvent
from backend.app.tasks.schemas import (
    TaskClaimRequest,
    TaskCompletionRequest,
    TaskCreateRequest,
    TaskFailureRequest,
)
from backend.app.tasks.state_machine import TaskStateMachine

logger = logging.getLogger(__name__)
MAX_TASK_METADATA_BYTES = 4096

_RESOLVABLE_PERMISSION_REASONS = frozenset(
    {
        DecisionReason.NO_PERMISSION,
        DecisionReason.PERMISSION_REVOKED,
        DecisionReason.PERMISSION_EXPIRED,
        DecisionReason.SCOPE_MISMATCH,
        DecisionReason.DEVICE_SCOPE_MISMATCH,
    }
)


@dataclass(frozen=True)
class TaskCreationResult:
    task: Task | None
    hard_denied: bool
    decision: AuthorizationDecision | None = None


class TaskService:
    """Create and mutate Task records without executing their represented actions."""

    def __init__(
        self,
        session: AsyncSession,
        permissions: PermissionsEngine,
        audit: AuditEngine,
    ) -> None:
        self.session = session
        self.permissions = permissions
        self.audit = audit

    async def create(
        self, identity: IdentityContext, request: TaskCreateRequest
    ) -> TaskCreationResult:
        """Resolve idempotency, authorize, and persist Task plus lifecycle evidence atomically."""
        existing = await self._idempotent_existing(
            identity.user_id, request.idempotency_key, request.fingerprint
        )
        if existing is not None:
            decision = await self.permissions.get_owned_decision(
                identity, existing.authorization_decision_id
            )
            return TaskCreationResult(existing, False, decision)

        now = utc_now()
        if request.expires_at is not None and at_or_after(now, request.expires_at):
            return TaskCreationResult(None, True)
        await self._validate_parent(identity.user_id, request.parent_task_id)
        device = await self._validate_device(identity.user_id, request.device_id)
        evaluation_identity = (
            identity.model_copy(update={"device_id": device.id}) if device is not None else identity
        )
        decision = await self.permissions.authorize(
            evaluation_identity,
            AuthorizationRequest(
                capability_key=request.capability_key,
                action=request.action,
                scope=request.scope,
            ),
        )
        initial = self._initial_state(decision.decision, decision.reason_codes)
        if initial is None:
            return TaskCreationResult(None, True, decision)
        status, reason = initial

        task = Task(
            user_id=identity.user_id,
            device_id=device.id if device else None,
            capability_key=request.capability_key,
            action=request.action,
            scope=request.scope.model_dump(mode="json"),
            scope_digest=request.scope.digest,
            status=status,
            priority=request.priority,
            idempotency_key=request.idempotency_key,
            request_fingerprint=request.fingerprint,
            authorization_decision_id=decision.decision_id,
            confirmation_request_id=decision.confirmation_id,
            parent_task_id=request.parent_task_id,
            created_at=now,
            updated_at=now,
            queued_at=now if status is TaskStatus.QUEUED else None,
            expires_at=request.expires_at,
            retry_count=0,
            max_retries=request.max_retries,
            version=1,
            metadata_payload=request.metadata,
            result_metadata={},
        )
        try:
            async with self.session.begin_nested():
                self.session.add(task)
                await self.session.flush()
                await self._append_event(
                    task,
                    event_type=TaskEventType.CREATED,
                    from_state=None,
                    to_state=status,
                    reason=reason,
                    actor_type=TaskActorType.USER,
                    actor_id=str(identity.user_id),
                )
                await self.audit.record(
                    self._audit_record(
                        identity,
                        task,
                        AuditEventType.TASK_CREATED,
                        AuditResult.RECORDED,
                        reason.value,
                    )
                )
                await self.session.flush()
        except IntegrityError:
            existing = await self._idempotent_existing(
                identity.user_id, request.idempotency_key, request.fingerprint
            )
            if existing is None:
                raise TaskConcurrentModificationError from None
            existing_decision = await self.permissions.get_owned_decision(
                identity, existing.authorization_decision_id
            )
            return TaskCreationResult(existing, False, existing_decision)

        logger.info(
            "Task created",
            extra={
                "task_id": str(task.id),
                "task_state": task.status.value,
                "capability_key": task.capability_key,
                "authorization_decision_id": str(task.authorization_decision_id),
                "user_id": str(task.user_id),
                "device_id": str(task.device_id) if task.device_id else None,
            },
        )
        return TaskCreationResult(task, False, decision)

    async def list_owned(
        self,
        identity: IdentityContext,
        *,
        status: TaskStatus | None,
        capability_key: str | None,
        limit: int,
        offset: int,
    ) -> list[Task]:
        query = select(Task).where(Task.user_id == identity.user_id)
        if status is not None:
            query = query.where(Task.status == status)
        if capability_key is not None:
            query = query.where(Task.capability_key == capability_key)
        tasks = list(
            await self.session.scalars(
                query.order_by(Task.created_at.desc(), Task.id.desc()).limit(limit).offset(offset)
            )
        )
        for task in tasks:
            await self._expire_if_due(task)
        return tasks

    async def get_owned(self, identity: IdentityContext, task_id: UUID) -> Task:
        task = await self._owned_task(identity.user_id, task_id)
        await self._expire_if_due(task)
        return task

    async def history(self, task: Task) -> tuple[list[TaskAttempt], list[TaskEvent]]:
        attempts = list(
            await self.session.scalars(
                select(TaskAttempt)
                .where(TaskAttempt.task_id == task.id)
                .order_by(TaskAttempt.attempt_number, TaskAttempt.id)
            )
        )
        events = list(
            await self.session.scalars(
                select(TaskEvent)
                .where(TaskEvent.task_id == task.id)
                .order_by(TaskEvent.timestamp, TaskEvent.id)
            )
        )
        return attempts, events

    async def cancel(self, identity: IdentityContext, task_id: UUID, expected_version: int) -> Task:
        task = await self._owned_task(identity.user_id, task_id)
        if await self._expire_if_due(task):
            return task
        if task.status is TaskStatus.CANCELLED:
            return task
        if TaskStateMachine.is_terminal(task.status):
            raise TaskAlreadyTerminalError
        task = await self._transition(
            task,
            TaskStatus.CANCELLED,
            expected_version=expected_version,
            event_type=TaskEventType.CANCELLED,
            reason=TaskTransitionReason.USER_CANCELLED,
            actor_type=TaskActorType.USER,
            actor_id=str(identity.user_id),
        )
        await self.audit.record(
            self._audit_record(
                identity,
                task,
                AuditEventType.TASK_CANCELLED,
                AuditResult.RECORDED,
                TaskTransitionReason.USER_CANCELLED.value,
            )
        )
        return task

    async def claim_task(
        self, task_id: UUID, request: TaskClaimRequest
    ) -> tuple[Task, TaskAttempt | None]:
        """Atomically claim QUEUED work for a future trusted worker boundary."""
        task = await self.session.get(Task, task_id)
        if task is None:
            raise TaskNotFoundError
        if await self._expire_if_due(task):
            return task, None
        if task.status is not TaskStatus.QUEUED:
            raise TaskNotClaimableError
        task = await self._transition(
            task,
            TaskStatus.RUNNING,
            expected_version=request.expected_version,
            event_type=TaskEventType.CLAIMED,
            reason=TaskTransitionReason.WORKER_CLAIMED,
            actor_type=TaskActorType.WORKER,
            actor_id=request.worker_id,
            metadata=request.metadata,
        )
        attempt = TaskAttempt(
            task_id=task.id,
            attempt_number=task.retry_count + 1,
            status=TaskAttemptStatus.RUNNING,
            started_at=task.started_at or utc_now(),
            worker_id=request.worker_id,
            execution_id=uuid4(),
            metadata_payload=request.metadata,
        )
        self.session.add(attempt)
        await self.session.flush()
        await self.audit.record(
            AuditRecord(
                user_id=task.user_id,
                device_id=task.device_id,
                actor_type=ActorType.SYSTEM,
                event_type=AuditEventType.TASK_CLAIMED,
                result=AuditResult.RECORDED,
                capability_key=task.capability_key,
                action=task.action,
                authorization_decision_id=task.authorization_decision_id,
                task_id=task.id,
                execution_id=attempt.execution_id,
                reason_codes=(TaskTransitionReason.WORKER_CLAIMED.value,),
            )
        )
        return task, attempt

    async def complete_task(self, task_id: UUID, request: TaskCompletionRequest) -> Task:
        task = await self._running_task(task_id)
        task = await self._transition(
            task,
            TaskStatus.COMPLETED,
            expected_version=request.expected_version,
            event_type=TaskEventType.COMPLETED,
            reason=TaskTransitionReason.EXECUTION_COMPLETED,
            actor_type=TaskActorType.WORKER,
            metadata=request.result_metadata,
            extra_values={"result_metadata": request.result_metadata},
        )
        attempt = await self._running_attempt(task.id)
        attempt.status = TaskAttemptStatus.COMPLETED
        attempt.finished_at = task.completed_at or utc_now()
        await self.session.flush()
        return task

    async def fail_task(self, task_id: UUID, request: TaskFailureRequest) -> Task:
        task = await self._running_task(task_id)
        task = await self._transition(
            task,
            TaskStatus.FAILED,
            expected_version=request.expected_version,
            event_type=TaskEventType.FAILED,
            reason=TaskTransitionReason.EXECUTION_FAILED,
            actor_type=TaskActorType.WORKER,
            metadata=request.metadata,
            extra_values={
                "last_error_code": request.error_code,
                "last_error_message": request.safe_error_message,
            },
        )
        attempt = await self._running_attempt(task.id)
        attempt.status = TaskAttemptStatus.FAILED
        attempt.finished_at = utc_now()
        attempt.error_code = request.error_code
        attempt.safe_error_message = request.safe_error_message
        await self.session.flush()
        return task

    async def reevaluate(
        self, identity: IdentityContext, task_id: UUID, expected_version: int
    ) -> Task:
        """Re-run Phase 2 authority for a permission/confirmation-blocked Task."""
        task = await self._owned_task(identity.user_id, task_id)
        if await self._expire_if_due(task):
            return task
        if task.status not in {TaskStatus.WAITING_PERMISSION, TaskStatus.WAITING_CONFIRMATION}:
            raise InvalidTaskTransitionError
        decision = await self.permissions.authorize(
            identity.model_copy(update={"device_id": task.device_id}),
            AuthorizationRequest(
                capability_key=task.capability_key,
                action=task.action,
                scope=PermissionScope.model_validate(task.scope),
                confirmation_id=task.confirmation_request_id,
            ),
        )
        initial = self._initial_state(decision.decision, decision.reason_codes)
        target = initial[0] if initial is not None else TaskStatus.FAILED
        if target is task.status:
            return task
        return await self._transition(
            task,
            target,
            expected_version=expected_version,
            event_type=TaskEventType.STATE_CHANGED,
            reason=TaskTransitionReason.AUTHORIZATION_REEVALUATED,
            actor_type=TaskActorType.SYSTEM,
            extra_values={
                "authorization_decision_id": decision.decision_id,
                "confirmation_request_id": decision.confirmation_id or task.confirmation_request_id,
                "last_error_code": (
                    "TASK_AUTHORIZATION_DENIED" if target is TaskStatus.FAILED else None
                ),
            },
        )

    @staticmethod
    def _initial_state(
        decision: AuthorizationDecisionType,
        reasons: tuple[DecisionReason, ...],
    ) -> tuple[TaskStatus, TaskTransitionReason] | None:
        if decision is AuthorizationDecisionType.ALLOW:
            return TaskStatus.QUEUED, TaskTransitionReason.CREATED_AUTHORIZED
        if decision is AuthorizationDecisionType.REQUIRE_CONFIRMATION:
            return (
                TaskStatus.WAITING_CONFIRMATION,
                TaskTransitionReason.CREATED_WAITING_CONFIRMATION,
            )
        if reasons and all(reason in _RESOLVABLE_PERMISSION_REASONS for reason in reasons):
            return (
                TaskStatus.WAITING_PERMISSION,
                TaskTransitionReason.CREATED_WAITING_PERMISSION,
            )
        return None

    async def _idempotent_existing(
        self, user_id: UUID, idempotency_key: str, fingerprint: str
    ) -> Task | None:
        existing = await self.session.scalar(
            select(Task).where(
                Task.user_id == user_id,
                Task.idempotency_key == idempotency_key,
            )
        )
        if existing is not None and existing.request_fingerprint != fingerprint:
            raise TaskIdempotencyConflictError
        return existing

    async def _validate_device(self, user_id: UUID, device_id: UUID | None) -> Device | None:
        if device_id is None:
            return None
        device = await self.session.scalar(
            select(Device).where(Device.id == device_id, Device.user_id == user_id)
        )
        if device is None or device.revoked_at is not None:
            raise TaskDeviceInvalidError
        return device

    async def _validate_parent(self, user_id: UUID, parent_task_id: UUID | None) -> None:
        if parent_task_id is None:
            return
        parent = await self.session.scalar(
            select(Task.id).where(Task.id == parent_task_id, Task.user_id == user_id)
        )
        if parent is None:
            raise TaskNotFoundError

    async def _owned_task(self, user_id: UUID, task_id: UUID) -> Task:
        task = await self.session.scalar(
            select(Task).where(Task.id == task_id, Task.user_id == user_id)
        )
        if task is None:
            raise TaskNotFoundError
        return task

    async def _running_task(self, task_id: UUID) -> Task:
        task = await self.session.get(Task, task_id)
        if task is None:
            raise TaskNotFoundError
        if task.status is not TaskStatus.RUNNING:
            if TaskStateMachine.is_terminal(task.status):
                raise TaskAlreadyTerminalError
            raise InvalidTaskTransitionError
        return task

    async def _running_attempt(self, task_id: UUID) -> TaskAttempt:
        attempt = await self.session.scalar(
            select(TaskAttempt).where(
                TaskAttempt.task_id == task_id,
                TaskAttempt.status == TaskAttemptStatus.RUNNING,
            )
        )
        if attempt is None:
            raise TaskConcurrentModificationError
        return attempt

    async def _expire_if_due(self, task: Task) -> bool:
        if (
            task.expires_at is None
            or TaskStateMachine.is_terminal(task.status)
            or not at_or_after(utc_now(), task.expires_at)
        ):
            return False
        await self._transition(
            task,
            TaskStatus.EXPIRED,
            expected_version=task.version,
            event_type=TaskEventType.EXPIRED,
            reason=TaskTransitionReason.DEADLINE_REACHED,
            actor_type=TaskActorType.SYSTEM,
        )
        return True

    async def _transition(
        self,
        task: Task,
        target: TaskStatus,
        *,
        expected_version: int,
        event_type: TaskEventType,
        reason: TaskTransitionReason,
        actor_type: TaskActorType,
        actor_id: str | None = None,
        metadata: dict[str, object] | None = None,
        extra_values: dict[str, object] | None = None,
    ) -> Task:
        evaluation = TaskStateMachine.evaluate(task.status, target)
        if not evaluation.allowed:
            if TaskStateMachine.is_terminal(task.status):
                raise TaskAlreadyTerminalError
            raise InvalidTaskTransitionError
        now = utc_now()
        values: dict[str, object] = {
            "status": target,
            "updated_at": now,
            "version": expected_version + 1,
        }
        if target is TaskStatus.QUEUED:
            values["queued_at"] = now
        elif target is TaskStatus.RUNNING:
            values["started_at"] = now
        elif target is TaskStatus.COMPLETED:
            values["completed_at"] = now
        elif target is TaskStatus.CANCELLED:
            values["cancelled_at"] = now
        if extra_values:
            values.update(extra_values)

        result = cast(
            CursorResult[tuple[object, ...]],
            await self.session.execute(
                update(Task)
                .where(
                    Task.id == task.id,
                    Task.status == task.status,
                    Task.version == expected_version,
                )
                .values(**values)
            ),
        )
        if result.rowcount != 1:
            raise TaskConcurrentModificationError
        previous = task.status
        await self.session.refresh(task)
        await self._append_event(
            task,
            event_type=event_type,
            from_state=previous,
            to_state=target,
            reason=reason,
            actor_type=actor_type,
            actor_id=actor_id,
            metadata=metadata,
        )
        return task

    async def _append_event(
        self,
        task: Task,
        *,
        event_type: TaskEventType,
        from_state: TaskStatus | None,
        to_state: TaskStatus,
        reason: TaskTransitionReason,
        actor_type: TaskActorType,
        actor_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> TaskEvent:
        event = TaskEvent(
            task_id=task.id,
            user_id=task.user_id,
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            timestamp=utc_now(),
            reason_code=reason.value,
            actor_type=actor_type,
            actor_id=actor_id,
            metadata_payload=sanitize_metadata(metadata or {}, max_bytes=MAX_TASK_METADATA_BYTES),
        )
        self.session.add(event)
        await self.session.flush()
        return event

    @staticmethod
    def _audit_record(
        identity: IdentityContext,
        task: Task,
        event_type: AuditEventType,
        result: AuditResult,
        reason_code: str,
    ) -> AuditRecord:
        return AuditRecord(
            user_id=identity.user_id,
            device_id=task.device_id,
            session_id=identity.session_id,
            actor_type=ActorType.USER,
            event_type=event_type,
            result=result,
            capability_key=task.capability_key,
            action=task.action,
            resource_type=PermissionScope.model_validate(task.scope).resource_type,
            authorization_decision_id=task.authorization_decision_id,
            confirmation_id=task.confirmation_request_id,
            task_id=task.id,
            reason_codes=(reason_code,),
        )
