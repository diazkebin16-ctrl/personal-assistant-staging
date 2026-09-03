"""Health endpoint integration tests."""

import asyncio

from fastapi import FastAPI
from httpx import ASGITransport, Response
from httpx import AsyncClient as HttpxAsyncClient

from backend.app.core.config import Environment, Settings
from backend.app.main import create_app


def request(application: FastAPI, path: str) -> Response:
    async def send_request() -> Response:
        async with application.router.lifespan_context(application):
            transport = ASGITransport(app=application)
            async with HttpxAsyncClient(transport=transport, base_url="http://test") as client:
                return await client.get(path)

    return asyncio.run(send_request())


def test_liveness_endpoint() -> None:
    application = create_app(Settings(environment=Environment.LOCAL))

    response = request(application, "/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "personal-assistant-backend",
    }


def test_readiness_endpoint_reports_only_checked_components() -> None:
    application = create_app(Settings(environment=Environment.LOCAL))

    response = request(application, "/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "personal-assistant-backend",
        "checks": {"application": {"status": "ready"}},
    }
