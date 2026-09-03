"""Narrow authenticated owner API; execution envelopes and low-level controls stay internal."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from backend.app.auth.dependencies import CurrentIdentity
from backend.app.orchestrator.dependencies import OrchestratorDependency
from backend.app.orchestrator.enums import OrchestrationState
from backend.app.orchestrator.schemas import (
    OrchestrationMutationRequest,
    OrchestrationRequest,
    OrchestrationResponse,
    OrchestrationResult,
)

router = APIRouter()


@router.post("/orchestrations", response_model=OrchestrationResult)
async def create_orchestration(
    request: OrchestrationRequest,
    identity: CurrentIdentity,
    service: OrchestratorDependency,
) -> OrchestrationResult:
    return await service.create(identity, request)


@router.get("/orchestrations", response_model=list[OrchestrationResponse])
async def list_orchestrations(
    identity: CurrentIdentity,
    service: OrchestratorDependency,
    state: OrchestrationState | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> list[OrchestrationResponse]:
    workflows = await service.list_owned(identity, state=state, limit=limit, offset=offset)
    return [OrchestrationResponse.from_model(workflow) for workflow in workflows]


@router.get("/orchestrations/{workflow_id}", response_model=OrchestrationResponse)
async def get_orchestration(
    workflow_id: UUID,
    identity: CurrentIdentity,
    service: OrchestratorDependency,
) -> OrchestrationResponse:
    return OrchestrationResponse.from_model(await service.get_owned(identity, workflow_id))


@router.post("/orchestrations/{workflow_id}/cancel", response_model=OrchestrationResponse)
async def cancel_orchestration(
    workflow_id: UUID,
    request: OrchestrationMutationRequest,
    identity: CurrentIdentity,
    service: OrchestratorDependency,
) -> OrchestrationResponse:
    workflow = await service.cancel(identity, workflow_id, request.expected_version)
    return OrchestrationResponse.from_model(workflow)


@router.post("/orchestrations/{workflow_id}/resume", response_model=OrchestrationResult)
async def resume_orchestration(
    workflow_id: UUID,
    request: OrchestrationMutationRequest,
    identity: CurrentIdentity,
    service: OrchestratorDependency,
) -> OrchestrationResult:
    return await service.resume(identity, workflow_id, request.expected_version)
