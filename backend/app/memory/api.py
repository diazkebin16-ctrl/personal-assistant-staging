"""Authenticated, owner-scoped, bounded Memory API."""

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse

from backend.app.auth.dependencies import CurrentIdentity
from backend.app.core.errors import ErrorCode, ErrorDetail, ErrorResponse
from backend.app.memory.dependencies import MemoryServiceDependency
from backend.app.memory.enums import MemoryClass, MemorySourceType, MemoryStatus
from backend.app.memory.schemas import (
    MemoryArchiveRequest,
    MemoryCreateRequest,
    MemoryResponse,
    MemoryRevisionResponse,
    MemoryUpdateRequest,
)
from backend.app.memory.service import MemoryOperationResult
from backend.app.permissions.enums import AuthorizationDecisionType

logger = logging.getLogger(__name__)
router = APIRouter()
RetrievalStatus = Literal["ACTIVE", "ARCHIVED", "EXPIRED"]


def _error(code: ErrorCode, message: str, status_code: int, **extra: object) -> JSONResponse:
    response = ErrorResponse(error=ErrorDetail(code=code, message=message))
    content = response.model_dump(mode="json")
    content.update(extra)
    return JSONResponse(status_code=status_code, content=content)


def _authorization_error(result: MemoryOperationResult[object]) -> JSONResponse | None:
    if result.decision.decision is AuthorizationDecisionType.ALLOW:
        return None
    if result.decision.decision is AuthorizationDecisionType.REQUIRE_CONFIRMATION:
        return _error(
            ErrorCode.MEMORY_CONFIRMATION_REQUIRED,
            "The memory operation requires explicit confirmation.",
            409,
            confirmation_id=(
                str(result.decision.confirmation_id) if result.decision.confirmation_id else None
            ),
        )
    return _error(
        ErrorCode.MEMORY_AUTHORIZATION_DENIED,
        "The memory operation is denied by the authorization boundary.",
        403,
    )


def _not_found() -> JSONResponse:
    return _error(ErrorCode.MEMORY_NOT_FOUND, "The memory is not available.", 404)


@router.post("/memories", response_model=MemoryResponse, status_code=201)
async def create_memory(
    request: MemoryCreateRequest,
    identity: CurrentIdentity,
    service: MemoryServiceDependency,
) -> MemoryResponse | JSONResponse:
    result = await service.create_explicit(identity, request)
    error = _authorization_error(result)
    if error is not None:
        return error
    if result.value is None:
        return _not_found()
    return MemoryResponse.from_model(result.value)


@router.get("/memories", response_model=list[MemoryResponse])
async def list_memories(
    identity: CurrentIdentity,
    service: MemoryServiceDependency,
    status: RetrievalStatus = "ACTIVE",
    memory_class: MemoryClass | None = None,
    source_type: MemorySourceType | None = None,
    subject: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    min_importance: Annotated[int | None, Query(ge=0, le=100)] = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> list[MemoryResponse] | JSONResponse:
    if (created_after is not None and created_after.tzinfo is None) or (
        created_before is not None and created_before.tzinfo is None
    ):
        return _error(ErrorCode.INVALID_MEMORY_DATA, "The memory query is invalid.", 422)
    normalized_after = created_after.astimezone(UTC) if created_after else None
    normalized_before = created_before.astimezone(UTC) if created_before else None
    if normalized_after and normalized_before and normalized_after > normalized_before:
        return _error(ErrorCode.INVALID_MEMORY_DATA, "The memory query is invalid.", 422)
    result = await service.list_owned(
        identity,
        status=MemoryStatus(status),
        memory_class=memory_class,
        source_type=source_type,
        subject=subject,
        min_importance=min_importance,
        created_after=normalized_after,
        created_before=normalized_before,
        limit=limit,
        offset=offset,
    )
    error = _authorization_error(result)
    if error is not None:
        return error
    return [MemoryResponse.from_model(memory) for memory in (result.value or [])]


@router.get("/memories/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: UUID,
    identity: CurrentIdentity,
    service: MemoryServiceDependency,
) -> MemoryResponse | JSONResponse:
    result = await service.get_owned(identity, memory_id)
    error = _authorization_error(result)
    if error is not None:
        return error
    if result.value is None:
        return _not_found()
    return MemoryResponse.from_model(result.value)


@router.get("/memories/{memory_id}/revisions", response_model=list[MemoryRevisionResponse])
async def get_memory_revisions(
    memory_id: UUID,
    identity: CurrentIdentity,
    service: MemoryServiceDependency,
) -> list[MemoryRevisionResponse] | JSONResponse:
    result = await service.revisions_owned(identity, memory_id)
    error = _authorization_error(result)
    if error is not None:
        return error
    if result.value is None:
        return _not_found()
    return [MemoryRevisionResponse.from_model(revision) for revision in result.value]


@router.patch("/memories/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: UUID,
    request: MemoryUpdateRequest,
    identity: CurrentIdentity,
    service: MemoryServiceDependency,
) -> MemoryResponse | JSONResponse:
    result = await service.update_owned(identity, memory_id, request)
    error = _authorization_error(result)
    if error is not None:
        return error
    if result.value is None:
        return _not_found()
    return MemoryResponse.from_model(result.value)


@router.post("/memories/{memory_id}/archive", response_model=MemoryResponse)
async def archive_memory(
    memory_id: UUID,
    request: MemoryArchiveRequest,
    identity: CurrentIdentity,
    service: MemoryServiceDependency,
) -> MemoryResponse | JSONResponse:
    result = await service.archive_owned(identity, memory_id, request)
    error = _authorization_error(result)
    if error is not None:
        return error
    if result.value is None:
        return _not_found()
    return MemoryResponse.from_model(result.value)


@router.delete("/memories/{memory_id}", response_model=None, status_code=204)
async def delete_memory(
    memory_id: UUID,
    identity: CurrentIdentity,
    service: MemoryServiceDependency,
    expected_version: Annotated[int, Query(ge=1)],
    confirmation_id: UUID | None = None,
) -> Response | JSONResponse:
    result = await service.delete_owned(
        identity,
        memory_id,
        expected_version=expected_version,
        confirmation_id=confirmation_id,
    )
    error = _authorization_error(result)
    if error is not None:
        return error
    if result.value is None:
        return _not_found()
    logger.info(
        "Memory deleted",
        extra={
            "memory_id": str(memory_id),
            "user_id": str(identity.user_id),
            "device_id": str(identity.device_id) if identity.device_id else None,
        },
    )
    return Response(status_code=204)
