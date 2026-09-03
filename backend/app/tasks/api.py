"""Authenticated owner-scoped Task Engine API."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.app.auth.dependencies import CurrentIdentity
from backend.app.core.errors import ErrorCode, ErrorDetail, ErrorResponse
from backend.app.permissions.schemas import CapabilityKey
from backend.app.tasks.dependencies import TaskServiceDependency
from backend.app.tasks.enums import TaskStatus
from backend.app.tasks.schemas import (
    TaskAttemptResponse,
    TaskCancelRequest,
    TaskCreateRequest,
    TaskDetailResponse,
    TaskEventResponse,
    TaskResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/tasks", response_model=TaskResponse)
async def create_task(
    request: TaskCreateRequest,
    identity: CurrentIdentity,
    service: TaskServiceDependency,
) -> TaskResponse | JSONResponse:
    result = await service.create(identity, request)
    if result.hard_denied or result.task is None:
        response = ErrorResponse(
            error=ErrorDetail(
                code=ErrorCode.TASK_AUTHORIZATION_DENIED,
                message="Task creation is denied by the authorization boundary.",
            )
        )
        return JSONResponse(status_code=403, content=response.model_dump(mode="json"))
    return TaskResponse.from_model(result.task)


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    identity: CurrentIdentity,
    service: TaskServiceDependency,
    status: TaskStatus | None = None,
    capability: CapabilityKey | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> list[TaskResponse]:
    tasks = await service.list_owned(
        identity,
        status=status,
        capability_key=capability,
        limit=limit,
        offset=offset,
    )
    return [TaskResponse.from_model(task) for task in tasks]


@router.get("/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task(
    task_id: UUID,
    identity: CurrentIdentity,
    service: TaskServiceDependency,
) -> TaskDetailResponse:
    task = await service.get_owned(identity, task_id)
    attempts, events = await service.history(task)
    return TaskDetailResponse(
        **TaskResponse.from_model(task).model_dump(),
        attempts=[TaskAttemptResponse.from_model(attempt) for attempt in attempts],
        events=[TaskEventResponse.from_model(event) for event in events],
    )


@router.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: UUID,
    request: TaskCancelRequest,
    identity: CurrentIdentity,
    service: TaskServiceDependency,
) -> TaskResponse:
    task = await service.cancel(identity, task_id, request.expected_version)
    logger.info(
        "Task cancellation evaluated",
        extra={
            "task_id": str(task.id),
            "task_state": task.status.value,
            "capability_key": task.capability_key,
            "authorization_decision_id": str(task.authorization_decision_id),
            "user_id": str(identity.user_id),
            "device_id": str(task.device_id) if task.device_id else None,
        },
    )
    return TaskResponse.from_model(task)
