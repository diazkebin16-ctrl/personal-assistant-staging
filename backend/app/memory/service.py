"""Transactional Memory Core with owner, authority, history, and privacy boundaries."""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.audit.engine import AuditEngine
from backend.app.audit.schemas import AuditRecord
from backend.app.core.errors import (
    InvalidMemoryDataError,
    MemoryConcurrentModificationError,
    MemoryDuplicateConflictError,
    MemoryImmutableError,
)
from backend.app.core.metadata import sanitize_metadata
from backend.app.core.time import at_or_after
from backend.app.identity.context import IdentityContext
from backend.app.identity.models import Device, utc_now
from backend.app.memory.enums import (
    MemoryActorType,
    MemoryClass,
    MemoryEventType,
    MemorySourceType,
    MemoryStatus,
)
from backend.app.memory.models import MemoryEvent, MemoryRecord, MemoryRevision
from backend.app.memory.schemas import (
    MAX_MEMORY_METADATA_BYTES,
    MemoryArchiveRequest,
    MemoryContextItem,
    MemoryContextPack,
    MemoryCreateRequest,
    MemoryProposal,
    MemoryUpdateRequest,
    memory_fingerprint,
    normalize_memory_text,
)
from backend.app.permissions.engine import PermissionsEngine
from backend.app.permissions.enums import (
    ActorType,
    AuditEventType,
    AuditResult,
    AuthorizationDecisionType,
)
from backend.app.permissions.schemas import (
    AuthorizationDecision,
    AuthorizationRequest,
    PermissionScope,
)
from backend.app.tasks.models import Task

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemoryOperationResult[T]:
    """Preserve authority decisions even when no memory operation is allowed."""

    value: T | None
    decision: AuthorizationDecision


class MemoryService:
    """Only server-owned methods may turn validated proposals into persisted memory."""

    def __init__(
        self,
        session: AsyncSession,
        permissions: PermissionsEngine,
        audit: AuditEngine,
    ) -> None:
        self.session = session
        self.permissions = permissions
        self.audit = audit

    async def create_explicit(
        self, identity: IdentityContext, request: MemoryCreateRequest
    ) -> MemoryOperationResult[MemoryRecord]:
        proposal = MemoryProposal(
            memory_class=request.memory_class,
            content=request.content,
            summary=request.summary,
            subject=request.subject,
            source_type=MemorySourceType.USER_EXPLICIT,
            source_reference=request.source_reference,
            source_device_id=request.source_device_id,
            confidence=100,
            importance=request.importance,
            sensitivity=request.sensitivity,
            expires_at=request.expires_at,
            metadata=request.metadata,
            confirmation_id=request.confirmation_id,
        )
        return await self._create(identity, proposal, MemoryActorType.USER)

    async def create_internal(
        self,
        identity: IdentityContext,
        proposal: MemoryProposal,
    ) -> MemoryOperationResult[MemoryRecord]:
        """Policy entry point for trusted future services; AI proposals remain non-authoritative."""
        if proposal.source_type in {
            MemorySourceType.USER_EXPLICIT,
            MemorySourceType.FUTURE_AI_PROPOSAL,
        }:
            raise InvalidMemoryDataError
        actor = (
            MemoryActorType.DEVICE
            if proposal.source_type is MemorySourceType.DEVICE
            else MemoryActorType.SYSTEM
        )
        return await self._create(identity, proposal, actor)

    async def _create(
        self,
        identity: IdentityContext,
        proposal: MemoryProposal,
        actor_type: MemoryActorType,
    ) -> MemoryOperationResult[MemoryRecord]:
        decision = await self._authorize(
            identity,
            capability_key="memory.write",
            action="create",
            confirmation_id=proposal.confirmation_id,
        )
        if decision.decision is not AuthorizationDecisionType.ALLOW:
            return MemoryOperationResult(None, decision)

        now = utc_now()
        if proposal.expires_at is not None and at_or_after(now, proposal.expires_at):
            raise InvalidMemoryDataError
        await self._validate_provenance(identity, proposal)

        normalized = normalize_memory_text(proposal.content)
        fingerprint = memory_fingerprint(proposal.memory_class, proposal.content, proposal.subject)
        deduplication_key = (
            None if proposal.memory_class is MemoryClass.HISTORICAL_DECISION else fingerprint
        )
        if deduplication_key is not None:
            existing = await self._active_duplicate(
                identity.user_id, proposal.memory_class, deduplication_key
            )
            if existing is not None:
                if await self._expire_if_due(existing):
                    existing = None
                else:
                    await self._append_event(
                        existing,
                        MemoryEventType.DEDUPLICATED,
                        from_status=MemoryStatus.ACTIVE,
                        to_status=MemoryStatus.ACTIVE,
                        actor_type=actor_type,
                        actor_id=str(identity.user_id),
                        reason_code="EXACT_CANONICAL_DUPLICATE",
                        metadata={"source_type": proposal.source_type.value},
                    )
                    return MemoryOperationResult(existing, decision)

        memory = MemoryRecord(
            user_id=identity.user_id,
            source_device_id=proposal.source_device_id,
            memory_class=proposal.memory_class,
            status=MemoryStatus.ACTIVE,
            source_type=proposal.source_type,
            source_reference=proposal.source_reference,
            content=proposal.content,
            normalized_content=normalized,
            summary=proposal.summary,
            subject=proposal.subject,
            confidence=proposal.confidence,
            importance=proposal.importance,
            sensitivity=proposal.sensitivity,
            fingerprint=fingerprint,
            deduplication_key=deduplication_key,
            created_at=now,
            updated_at=now,
            expires_at=proposal.expires_at,
            version=1,
            metadata_payload=proposal.metadata,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(memory)
                await self.session.flush()
                await self._append_event(
                    memory,
                    MemoryEventType.CREATED,
                    from_status=None,
                    to_status=MemoryStatus.ACTIVE,
                    actor_type=actor_type,
                    actor_id=str(identity.user_id),
                    reason_code="MEMORY_STORED",
                )
                await self.audit.record(
                    self._audit_record(
                        identity,
                        memory,
                        decision,
                        AuditEventType.MEMORY_CREATED,
                        "MEMORY_STORED",
                    )
                )
        except IntegrityError:
            if deduplication_key is None:
                raise MemoryConcurrentModificationError from None
            existing = await self._active_duplicate(
                identity.user_id, proposal.memory_class, deduplication_key
            )
            if existing is None:
                raise MemoryConcurrentModificationError from None
            return MemoryOperationResult(existing, decision)

        logger.info(
            "Memory created",
            extra={
                "memory_id": str(memory.id),
                "memory_class": memory.memory_class.value,
                "user_id": str(memory.user_id),
                "device_id": str(memory.source_device_id) if memory.source_device_id else None,
            },
        )
        return MemoryOperationResult(memory, decision)

    async def list_owned(
        self,
        identity: IdentityContext,
        *,
        status: MemoryStatus,
        memory_class: MemoryClass | None,
        source_type: MemorySourceType | None,
        subject: str | None,
        min_importance: int | None,
        created_after: datetime | None,
        created_before: datetime | None,
        limit: int,
        offset: int,
    ) -> MemoryOperationResult[list[MemoryRecord]]:
        decision = await self._authorize(identity, capability_key="memory.read", action="read")
        if decision.decision is not AuthorizationDecisionType.ALLOW:
            return MemoryOperationResult(None, decision)
        await self._materialize_due_expirations(identity.user_id)
        query: Select[tuple[MemoryRecord]] = select(MemoryRecord).where(
            MemoryRecord.user_id == identity.user_id,
            MemoryRecord.status == status,
        )
        if memory_class is None and status is MemoryStatus.ACTIVE:
            query = query.where(MemoryRecord.memory_class != MemoryClass.DISCARDABLE)
        elif memory_class is not None:
            query = query.where(MemoryRecord.memory_class == memory_class)
        if source_type is not None:
            query = query.where(MemoryRecord.source_type == source_type)
        if subject is not None:
            query = query.where(MemoryRecord.subject == subject)
        if min_importance is not None:
            query = query.where(MemoryRecord.importance >= min_importance)
        if created_after is not None:
            query = query.where(MemoryRecord.created_at >= created_after)
        if created_before is not None:
            query = query.where(MemoryRecord.created_at <= created_before)
        records = list(
            await self.session.scalars(
                query.order_by(MemoryRecord.created_at.desc(), MemoryRecord.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return MemoryOperationResult(records, decision)

    async def get_owned(
        self, identity: IdentityContext, memory_id: UUID
    ) -> MemoryOperationResult[MemoryRecord]:
        decision = await self._authorize(identity, capability_key="memory.read", action="read")
        if decision.decision is not AuthorizationDecisionType.ALLOW:
            return MemoryOperationResult(None, decision)
        memory = await self.session.scalar(
            select(MemoryRecord).where(
                MemoryRecord.id == memory_id,
                MemoryRecord.user_id == identity.user_id,
                MemoryRecord.status == MemoryStatus.ACTIVE,
            )
        )
        if memory is not None and await self._expire_if_due(memory):
            memory = None
        return MemoryOperationResult(memory, decision)

    async def update_owned(
        self,
        identity: IdentityContext,
        memory_id: UUID,
        request: MemoryUpdateRequest,
    ) -> MemoryOperationResult[MemoryRecord]:
        decision = await self._authorize(
            identity,
            capability_key="memory.write",
            action="update",
            confirmation_id=request.confirmation_id,
        )
        if decision.decision is not AuthorizationDecisionType.ALLOW:
            return MemoryOperationResult(None, decision)
        memory = await self._active_owned(identity.user_id, memory_id)
        if memory is None or await self._expire_if_due(memory):
            return MemoryOperationResult(None, decision)
        if memory.memory_class is MemoryClass.HISTORICAL_DECISION:
            raise MemoryImmutableError
        if memory.version != request.expected_version:
            raise MemoryConcurrentModificationError

        values: dict[str, object] = {}
        fields = request.model_fields_set
        for field in ("summary", "subject", "importance", "sensitivity", "expires_at"):
            if field in fields:
                values[field] = getattr(request, field)
        if "metadata" in fields:
            values["metadata_payload"] = request.metadata or {}
        content = cast(str, request.content) if "content" in fields else memory.content
        subject = request.subject if "subject" in fields else memory.subject
        if "content" in fields:
            values["content"] = content
            values["normalized_content"] = normalize_memory_text(content)
        if "content" in fields or "subject" in fields:
            fingerprint = memory_fingerprint(memory.memory_class, content, subject)
            values["fingerprint"] = fingerprint
            values["deduplication_key"] = fingerprint
        expires_at = request.expires_at if "expires_at" in fields else memory.expires_at
        if memory.memory_class is MemoryClass.TEMPORARY_CONTEXT and expires_at is None:
            raise InvalidMemoryDataError
        if expires_at is not None and at_or_after(utc_now(), expires_at):
            raise InvalidMemoryDataError

        now = utc_now()
        values.update(updated_at=now, version=request.expected_version + 1)
        revision = self._revision_snapshot(memory)
        try:
            async with self.session.begin_nested():
                self.session.add(revision)
                result = cast(
                    CursorResult[tuple[object, ...]],
                    await self.session.execute(
                        update(MemoryRecord)
                        .where(
                            MemoryRecord.id == memory.id,
                            MemoryRecord.user_id == identity.user_id,
                            MemoryRecord.status == MemoryStatus.ACTIVE,
                            MemoryRecord.version == request.expected_version,
                        )
                        .values(**values)
                    ),
                )
                if result.rowcount != 1:
                    raise MemoryConcurrentModificationError
                await self.session.refresh(memory)
                await self._append_event(
                    memory,
                    MemoryEventType.UPDATED,
                    from_status=MemoryStatus.ACTIVE,
                    to_status=MemoryStatus.ACTIVE,
                    actor_type=MemoryActorType.USER,
                    actor_id=str(identity.user_id),
                    reason_code="EXPLICIT_UPDATE",
                    metadata={"previous_version": request.expected_version},
                )
                await self.audit.record(
                    self._audit_record(
                        identity,
                        memory,
                        decision,
                        AuditEventType.MEMORY_UPDATED,
                        "EXPLICIT_UPDATE",
                    )
                )
        except IntegrityError:
            raise MemoryDuplicateConflictError from None
        return MemoryOperationResult(memory, decision)

    async def archive_owned(
        self,
        identity: IdentityContext,
        memory_id: UUID,
        request: MemoryArchiveRequest,
    ) -> MemoryOperationResult[MemoryRecord]:
        decision = await self._authorize(
            identity,
            capability_key="memory.write",
            action="archive",
            confirmation_id=request.confirmation_id,
        )
        if decision.decision is not AuthorizationDecisionType.ALLOW:
            return MemoryOperationResult(None, decision)
        memory = await self._owned_non_deleted(identity.user_id, memory_id)
        if memory is None:
            return MemoryOperationResult(None, decision)
        if memory.status is MemoryStatus.ARCHIVED:
            return MemoryOperationResult(memory, decision)
        if memory.status is MemoryStatus.EXPIRED or await self._expire_if_due(memory):
            return MemoryOperationResult(None, decision)
        if memory.version != request.expected_version:
            raise MemoryConcurrentModificationError
        now = utc_now()
        result = cast(
            CursorResult[tuple[object, ...]],
            await self.session.execute(
                update(MemoryRecord)
                .where(
                    MemoryRecord.id == memory.id,
                    MemoryRecord.user_id == identity.user_id,
                    MemoryRecord.status == MemoryStatus.ACTIVE,
                    MemoryRecord.version == request.expected_version,
                )
                .values(
                    status=MemoryStatus.ARCHIVED,
                    archived_at=now,
                    updated_at=now,
                    version=request.expected_version + 1,
                )
            ),
        )
        if result.rowcount != 1:
            raise MemoryConcurrentModificationError
        await self.session.refresh(memory)
        await self._append_event(
            memory,
            MemoryEventType.ARCHIVED,
            from_status=MemoryStatus.ACTIVE,
            to_status=MemoryStatus.ARCHIVED,
            actor_type=MemoryActorType.USER,
            actor_id=str(identity.user_id),
            reason_code="USER_ARCHIVED",
        )
        await self.audit.record(
            self._audit_record(
                identity,
                memory,
                decision,
                AuditEventType.MEMORY_ARCHIVED,
                "USER_ARCHIVED",
            )
        )
        return MemoryOperationResult(memory, decision)

    async def delete_owned(
        self,
        identity: IdentityContext,
        memory_id: UUID,
        *,
        expected_version: int,
        confirmation_id: UUID | None,
    ) -> MemoryOperationResult[MemoryRecord]:
        decision = await self._authorize(
            identity,
            capability_key="memory.delete",
            action="delete",
            confirmation_id=confirmation_id,
        )
        if decision.decision is not AuthorizationDecisionType.ALLOW:
            return MemoryOperationResult(None, decision)
        memory = await self.session.scalar(
            select(MemoryRecord).where(
                MemoryRecord.id == memory_id, MemoryRecord.user_id == identity.user_id
            )
        )
        if memory is None:
            return MemoryOperationResult(None, decision)
        if memory.status is MemoryStatus.DELETED:
            return MemoryOperationResult(memory, decision)
        if memory.version != expected_version:
            raise MemoryConcurrentModificationError

        now = utc_now()
        tombstone = hashlib.sha256(f"deleted:{memory.id}".encode()).hexdigest()
        previous = memory.status
        result = cast(
            CursorResult[tuple[object, ...]],
            await self.session.execute(
                update(MemoryRecord)
                .where(
                    MemoryRecord.id == memory.id,
                    MemoryRecord.user_id == identity.user_id,
                    MemoryRecord.status != MemoryStatus.DELETED,
                    MemoryRecord.version == expected_version,
                )
                .values(
                    status=MemoryStatus.DELETED,
                    content="[DELETED]",
                    normalized_content=None,
                    summary=None,
                    subject=None,
                    source_reference=None,
                    fingerprint=tombstone,
                    deduplication_key=None,
                    metadata_payload={},
                    deleted_at=now,
                    updated_at=now,
                    version=expected_version + 1,
                )
            ),
        )
        if result.rowcount != 1:
            raise MemoryConcurrentModificationError
        await self.session.execute(
            update(MemoryRevision)
            .where(MemoryRevision.memory_id == memory.id)
            .values(
                content="[DELETED]",
                normalized_content=None,
                summary=None,
                subject=None,
                source_reference=None,
                fingerprint=tombstone,
                metadata_payload={},
            )
        )
        await self.session.refresh(memory)
        await self._append_event(
            memory,
            MemoryEventType.DELETED,
            from_status=previous,
            to_status=MemoryStatus.DELETED,
            actor_type=MemoryActorType.USER,
            actor_id=str(identity.user_id),
            reason_code="PRIVACY_DELETE",
        )
        await self.audit.record(
            self._audit_record(
                identity,
                memory,
                decision,
                AuditEventType.MEMORY_DELETED,
                "PRIVACY_DELETE",
            )
        )
        return MemoryOperationResult(memory, decision)

    async def revisions_owned(
        self, identity: IdentityContext, memory_id: UUID
    ) -> MemoryOperationResult[list[MemoryRevision]]:
        decision = await self._authorize(identity, capability_key="memory.read", action="read")
        if decision.decision is not AuthorizationDecisionType.ALLOW:
            return MemoryOperationResult(None, decision)
        owned = await self.session.scalar(
            select(MemoryRecord.id).where(
                MemoryRecord.id == memory_id,
                MemoryRecord.user_id == identity.user_id,
                MemoryRecord.status != MemoryStatus.DELETED,
            )
        )
        if owned is None:
            return MemoryOperationResult(None, decision)
        revisions = list(
            await self.session.scalars(
                select(MemoryRevision)
                .where(MemoryRevision.memory_id == memory_id)
                .order_by(MemoryRevision.revision_number, MemoryRevision.id)
            )
        )
        return MemoryOperationResult(revisions, decision)

    async def build_context_pack(
        self,
        identity: IdentityContext,
        *,
        per_category_limit: int = 5,
    ) -> MemoryOperationResult[MemoryContextPack]:
        """Build a deterministic maximum-20-item pack for a future Orchestrator boundary."""
        if not 1 <= per_category_limit <= 5:
            raise InvalidMemoryDataError
        decision = await self._authorize(identity, capability_key="memory.read", action="read")
        if decision.decision is not AuthorizationDecisionType.ALLOW:
            return MemoryOperationResult(None, decision)
        await self._materialize_due_expirations(identity.user_id)

        async def items(memory_class: MemoryClass) -> tuple[MemoryContextItem, ...]:
            records = list(
                await self.session.scalars(
                    select(MemoryRecord)
                    .where(
                        MemoryRecord.user_id == identity.user_id,
                        MemoryRecord.status == MemoryStatus.ACTIVE,
                        MemoryRecord.memory_class == memory_class,
                    )
                    .order_by(
                        MemoryRecord.importance.desc(),
                        MemoryRecord.updated_at.desc(),
                        MemoryRecord.id,
                    )
                    .limit(per_category_limit)
                )
            )
            return tuple(
                MemoryContextItem(
                    id=memory.id,
                    memory_class=memory.memory_class,
                    source_type=memory.source_type,
                    source_reference=memory.source_reference,
                    subject=memory.subject,
                    text=memory.summary or memory.content,
                    importance=memory.importance,
                    sensitivity=memory.sensitivity,
                    updated_at=memory.updated_at,
                )
                for memory in records
            )

        pack = MemoryContextPack(
            persistent_preferences=await items(MemoryClass.PERSISTENT_PREFERENCE),
            operational_context=await items(MemoryClass.OPERATIONAL),
            historical_decisions=await items(MemoryClass.HISTORICAL_DECISION),
            temporary_context=await items(MemoryClass.TEMPORARY_CONTEXT),
        )
        return MemoryOperationResult(pack, decision)

    async def _authorize(
        self,
        identity: IdentityContext,
        *,
        capability_key: str,
        action: str,
        confirmation_id: UUID | None = None,
    ) -> AuthorizationDecision:
        return await self.permissions.authorize(
            identity,
            AuthorizationRequest(
                capability_key=capability_key,
                action=action,
                scope=PermissionScope(resource_type="memory", operations=[action]),
                confirmation_id=confirmation_id,
            ),
        )

    async def _validate_provenance(
        self, identity: IdentityContext, proposal: MemoryProposal
    ) -> None:
        if proposal.source_device_id is not None:
            device = await self.session.scalar(
                select(Device).where(
                    Device.id == proposal.source_device_id,
                    Device.user_id == identity.user_id,
                )
            )
            if device is None or device.revoked_at is not None:
                raise InvalidMemoryDataError
        if proposal.source_type is MemorySourceType.TASK:
            try:
                task_id = UUID(proposal.source_reference or "")
            except ValueError:
                raise InvalidMemoryDataError from None
            task = await self.session.scalar(
                select(Task.id).where(Task.id == task_id, Task.user_id == identity.user_id)
            )
            if task is None:
                raise InvalidMemoryDataError

    async def _materialize_due_expirations(self, user_id: UUID) -> None:
        due = list(
            await self.session.scalars(
                select(MemoryRecord).where(
                    MemoryRecord.user_id == user_id,
                    MemoryRecord.status == MemoryStatus.ACTIVE,
                    MemoryRecord.expires_at.is_not(None),
                    MemoryRecord.expires_at <= utc_now(),
                )
            )
        )
        for memory in due:
            await self._expire_if_due(memory)

    async def _expire_if_due(self, memory: MemoryRecord) -> bool:
        if (
            memory.status is not MemoryStatus.ACTIVE
            or memory.expires_at is None
            or not at_or_after(utc_now(), memory.expires_at)
        ):
            return memory.status is MemoryStatus.EXPIRED
        previous_version = memory.version
        now = utc_now()
        result = cast(
            CursorResult[tuple[object, ...]],
            await self.session.execute(
                update(MemoryRecord)
                .where(
                    MemoryRecord.id == memory.id,
                    MemoryRecord.status == MemoryStatus.ACTIVE,
                    MemoryRecord.version == previous_version,
                )
                .values(
                    status=MemoryStatus.EXPIRED,
                    updated_at=now,
                    version=previous_version + 1,
                    deduplication_key=None,
                )
            ),
        )
        if result.rowcount != 1:
            await self.session.refresh(memory)
            return memory.status.value == MemoryStatus.EXPIRED.value
        await self.session.refresh(memory)
        await self._append_event(
            memory,
            MemoryEventType.EXPIRED,
            from_status=MemoryStatus.ACTIVE,
            to_status=MemoryStatus.EXPIRED,
            actor_type=MemoryActorType.SYSTEM,
            actor_id=None,
            reason_code="EXPIRATION_OBSERVED",
        )
        return True

    async def _append_event(
        self,
        memory: MemoryRecord,
        event_type: MemoryEventType,
        *,
        from_status: MemoryStatus | None,
        to_status: MemoryStatus,
        actor_type: MemoryActorType,
        actor_id: str | None,
        reason_code: str,
        metadata: dict[str, object] | None = None,
    ) -> MemoryEvent:
        event = MemoryEvent(
            memory_id=memory.id,
            user_id=memory.user_id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            timestamp=utc_now(),
            actor_type=actor_type,
            actor_id=actor_id,
            reason_code=reason_code,
            metadata_payload=sanitize_metadata(metadata or {}, max_bytes=MAX_MEMORY_METADATA_BYTES),
        )
        self.session.add(event)
        await self.session.flush()
        return event

    @staticmethod
    def _revision_snapshot(memory: MemoryRecord) -> MemoryRevision:
        return MemoryRevision(
            memory_id=memory.id,
            revision_number=memory.version,
            memory_class=memory.memory_class,
            source_type=memory.source_type,
            source_reference=memory.source_reference,
            content=memory.content,
            normalized_content=memory.normalized_content,
            summary=memory.summary,
            subject=memory.subject,
            confidence=memory.confidence,
            importance=memory.importance,
            sensitivity=memory.sensitivity,
            expires_at=memory.expires_at,
            fingerprint=memory.fingerprint,
            recorded_at=utc_now(),
            actor_type=MemoryActorType.USER,
            metadata_payload=memory.metadata_payload,
        )

    @staticmethod
    def _audit_record(
        identity: IdentityContext,
        memory: MemoryRecord,
        decision: AuthorizationDecision,
        event_type: AuditEventType,
        reason_code: str,
    ) -> AuditRecord:
        return AuditRecord(
            user_id=identity.user_id,
            device_id=memory.source_device_id or identity.device_id,
            session_id=identity.session_id,
            actor_type=ActorType.USER,
            event_type=event_type,
            result=AuditResult.RECORDED,
            capability_key={
                AuditEventType.MEMORY_DELETED: "memory.delete",
                AuditEventType.MEMORY_CREATED: "memory.write",
                AuditEventType.MEMORY_UPDATED: "memory.write",
                AuditEventType.MEMORY_ARCHIVED: "memory.write",
            }[event_type],
            action={
                AuditEventType.MEMORY_DELETED: "delete",
                AuditEventType.MEMORY_CREATED: "create",
                AuditEventType.MEMORY_UPDATED: "update",
                AuditEventType.MEMORY_ARCHIVED: "archive",
            }[event_type],
            resource_type="memory",
            resource_id=str(memory.id),
            risk_level=decision.risk_level,
            permission_id=decision.permission_id,
            authorization_decision_id=decision.decision_id,
            confirmation_id=decision.confirmation_id,
            reason_codes=(reason_code,),
            metadata={
                "memory_class": memory.memory_class.value,
                "sensitivity": memory.sensitivity.value,
            },
        )

    async def _active_duplicate(
        self, user_id: UUID, memory_class: MemoryClass, key: str
    ) -> MemoryRecord | None:
        return cast(
            MemoryRecord | None,
            await self.session.scalar(
                select(MemoryRecord).where(
                    MemoryRecord.user_id == user_id,
                    MemoryRecord.memory_class == memory_class,
                    MemoryRecord.deduplication_key == key,
                    MemoryRecord.status == MemoryStatus.ACTIVE,
                )
            ),
        )

    async def _active_owned(self, user_id: UUID, memory_id: UUID) -> MemoryRecord | None:
        return cast(
            MemoryRecord | None,
            await self.session.scalar(
                select(MemoryRecord).where(
                    MemoryRecord.id == memory_id,
                    MemoryRecord.user_id == user_id,
                    MemoryRecord.status == MemoryStatus.ACTIVE,
                )
            ),
        )

    async def _owned_non_deleted(self, user_id: UUID, memory_id: UUID) -> MemoryRecord | None:
        return cast(
            MemoryRecord | None,
            await self.session.scalar(
                select(MemoryRecord).where(
                    MemoryRecord.id == memory_id,
                    MemoryRecord.user_id == user_id,
                    MemoryRecord.status != MemoryStatus.DELETED,
                )
            ),
        )
