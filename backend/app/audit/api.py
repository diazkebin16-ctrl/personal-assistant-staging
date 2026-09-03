"""Read-only API for a user's own append-oriented audit events."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from backend.app.audit.models import AuditEvent
from backend.app.audit.schemas import AuditEventResponse
from backend.app.auth.dependencies import CurrentIdentity
from backend.app.identity.dependencies import DatabaseSession

router = APIRouter()


@router.get("/audit", response_model=list[AuditEventResponse])
async def list_audit_events(
    identity: CurrentIdentity,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> list[AuditEventResponse]:
    events = await session.scalars(
        select(AuditEvent)
        .where(AuditEvent.user_id == identity.user_id)
        .order_by(AuditEvent.timestamp.desc(), AuditEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [AuditEventResponse.from_model(event) for event in events]
