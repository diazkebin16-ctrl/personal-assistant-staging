"""Process liveness and application readiness endpoints."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from backend.app.core.config import Settings

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    """Liveness response for process-level health checks."""

    status: Literal["healthy"]
    service: str


class ComponentCheck(BaseModel):
    """Result for one component that was actually checked."""

    status: Literal["ready"]


class ReadinessResponse(BaseModel):
    """Readiness result with an extensible component-check map."""

    status: Literal["ready"]
    service: str
    checks: dict[str, ComponentCheck]


def get_runtime_settings(request: Request) -> Settings:
    """Return the settings attached by the application factory."""
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise RuntimeError("Application settings are unavailable")
    return settings


RuntimeSettings = Annotated[Settings, Depends(get_runtime_settings)]


@router.get("/live", response_model=LivenessResponse)
def liveness(settings: RuntimeSettings) -> LivenessResponse:
    """Confirm that the API process can serve a request."""
    return LivenessResponse(status="healthy", service=settings.app_name)


@router.get("/ready", response_model=ReadinessResponse)
def readiness(settings: RuntimeSettings) -> ReadinessResponse:
    """Report only readiness checks performed in the current phase."""
    return ReadinessResponse(
        status="ready",
        service=settings.app_name,
        checks={"application": ComponentCheck(status="ready")},
    )
