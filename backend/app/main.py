"""FastAPI application factory and default ASGI application."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.api.health import router as health_router
from backend.app.api.v1 import router as api_v1_router
from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import (
    ApplicationError,
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
)
from backend.app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an isolated application instance with validated configuration."""
    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("Application startup complete")
        yield
        logger.info("Application shutdown complete")

    application = FastAPI(
        title=runtime_settings.app_name,
        version=runtime_settings.app_version,
        lifespan=lifespan,
    )
    application.state.settings = runtime_settings
    application.include_router(health_router)
    application.include_router(api_v1_router)

    @application.exception_handler(ApplicationError)
    async def application_error_handler(_: Request, error: ApplicationError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if error.status_code == 401 else None
        response = ErrorResponse(error=ErrorDetail(code=error.code, message=error.message))
        return JSONResponse(
            status_code=error.status_code,
            content=response.model_dump(mode="json"),
            headers=headers,
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request,
        _: RequestValidationError,
    ) -> JSONResponse:
        is_device_request = request.url.path.startswith("/api/v1/devices")
        is_permission_request = request.url.path.startswith(
            ("/api/v1/permissions", "/api/v1/authorization", "/api/v1/confirmations")
        )
        is_task_request = request.url.path.startswith("/api/v1/tasks")
        is_memory_request = request.url.path.startswith("/api/v1/memories")
        is_orchestration_request = request.url.path.startswith("/api/v1/orchestrations")
        is_conversation_request = request.url.path.startswith("/api/v1/conversations")
        is_voice_request = request.url.path.startswith("/api/v1/voice")
        if is_device_request:
            code = ErrorCode.INVALID_DEVICE_DATA
            message = "The device data is invalid."
        elif is_permission_request:
            code = ErrorCode.INVALID_PERMISSION_DATA
            message = "The permission or authorization data is invalid."
        elif is_task_request:
            code = ErrorCode.INVALID_TASK_DATA
            message = "The task data is invalid."
        elif is_memory_request:
            code = ErrorCode.INVALID_MEMORY_DATA
            message = "The memory data is invalid."
        elif is_orchestration_request:
            code = ErrorCode.INVALID_ORCHESTRATION_DATA
            message = "The orchestration data is invalid."
        elif is_voice_request:
            code = ErrorCode.INVALID_VOICE_DATA
            message = "The voice session data is invalid."
        elif is_conversation_request:
            code = ErrorCode.INVALID_CONVERSATION_DATA
            message = "The conversation data is invalid."
        else:
            code = ErrorCode.INVALID_REQUEST
            message = "The request is invalid."
        response = ErrorResponse(error=ErrorDetail(code=code, message=message))
        return JSONResponse(status_code=422, content=response.model_dump(mode="json"))

    return application


app = create_app()
