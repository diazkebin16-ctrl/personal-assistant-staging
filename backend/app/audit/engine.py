"""Append-only audit writer with bounded, redacted metadata."""

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.audit.models import AuditEvent
from backend.app.audit.schemas import AuditRecord
from backend.app.core.errors import AuditUnavailableError
from backend.app.core.metadata import sanitize_metadata

MAX_AUDIT_METADATA_BYTES = 4096


class AuditEngine:
    """Append security evidence to the current authorization transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(self, record: AuditRecord) -> AuditEvent:
        sanitized = sanitize_metadata(record.metadata, max_bytes=MAX_AUDIT_METADATA_BYTES)

        event = AuditEvent(
            user_id=record.user_id,
            device_id=record.device_id,
            session_id=record.session_id,
            actor_type=record.actor_type,
            event_type=record.event_type,
            capability_key=record.capability_key,
            action=record.action,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            risk_level=(int(record.risk_level) if record.risk_level is not None else None),
            permission_id=record.permission_id,
            authorization_decision_id=record.authorization_decision_id,
            confirmation_id=record.confirmation_id,
            result=record.result,
            reason_codes=list(record.reason_codes),
            trace_id=record.trace_id,
            task_id=record.task_id,
            execution_id=record.execution_id,
            metadata_payload=sanitized,
        )
        self.session.add(event)
        try:
            await self.session.flush()
        except SQLAlchemyError:
            raise AuditUnavailableError from None
        return event
