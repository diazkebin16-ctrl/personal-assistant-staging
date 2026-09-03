"""Authentication boundary and identity-spoofing security tests."""

import asyncio
from uuid import uuid4

from httpx import ASGITransport
from httpx import AsyncClient as HttpxAsyncClient

from backend.app.core.config import Environment, Settings
from backend.app.main import create_app
from tests.helpers import api_client, bearer, make_claims


def test_missing_token_stops_before_external_auth_or_database_configuration() -> None:
    async def scenario() -> None:
        application = create_app(Settings(environment=Environment.LOCAL))
        transport = ASGITransport(app=application)
        async with application.router.lifespan_context(application):
            async with HttpxAsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                response = await client.get("/api/v1/me")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    asyncio.run(scenario())


def test_missing_bearer_token_is_401() -> None:
    async def scenario() -> None:
        async with api_client({"user-a": make_claims()}) as (client, _, _):
            response = await client.get("/api/v1/me")

            assert response.status_code == 401
            assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
            assert response.headers["www-authenticate"] == "Bearer"

    asyncio.run(scenario())


def test_malformed_authorization_header_is_401() -> None:
    async def scenario() -> None:
        async with api_client({"user-a": make_claims()}) as (client, _, _):
            response = await client.get(
                "/api/v1/me",
                headers={"Authorization": "Basic invalid"},
            )

            assert response.status_code == 401
            assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    asyncio.run(scenario())


def test_invalid_token_is_not_reflected_in_response() -> None:
    async def scenario() -> None:
        async with api_client({}) as (client, _, _):
            sensitive_value = "sensitive-fake-access-token"
            response = await client.get("/api/v1/me", headers=bearer(sensitive_value))

            assert response.status_code == 401
            assert response.json()["error"]["code"] == "INVALID_TOKEN"
            assert sensitive_value not in response.text

    asyncio.run(scenario())


def test_client_supplied_user_authority_is_rejected() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="spoof-body")
        async with api_client({"user-a": claims}) as (client, _, _):
            response = await client.post(
                "/api/v1/devices/register",
                headers=bearer("user-a"),
                json={
                    "user_id": str(uuid4()),
                    "device_name": "Spoof",
                    "device_type": "WEB",
                    "platform": "WEB",
                    "device_identifier": "spoof-installation",
                    "capabilities": {},
                },
            )

            assert response.status_code == 422
            assert response.json()["error"]["code"] == "INVALID_DEVICE_DATA"

    asyncio.run(scenario())


def test_client_identity_header_cannot_override_verified_token() -> None:
    async def scenario() -> None:
        auth_user_id = uuid4()
        claims = make_claims(auth_user_id=auth_user_id, session_id="spoof-header")
        async with api_client({"user-a": claims}) as (client, _, _):
            response = await client.get(
                "/api/v1/me",
                headers={
                    **bearer("user-a"),
                    "X-User-ID": str(uuid4()),
                },
            )

            assert response.status_code == 200
            assert response.json()["authenticated"] is True

    asyncio.run(scenario())


def test_invalid_device_manifests_are_rejected() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="invalid-device")
        async with api_client({"user-a": claims}) as (client, _, _):
            too_many_capabilities = {f"capability_{index}": True for index in range(33)}
            oversized = await client.post(
                "/api/v1/devices/register",
                headers=bearer("user-a"),
                json={
                    "device_name": "Invalid",
                    "device_type": "WEB",
                    "platform": "WEB",
                    "device_identifier": "invalid-capabilities",
                    "capabilities": too_many_capabilities,
                },
            )
            private_key = await client.post(
                "/api/v1/devices/register",
                headers=bearer("user-a"),
                json={
                    "device_name": "Invalid",
                    "device_type": "WEB",
                    "platform": "WEB",
                    "device_identifier": "invalid-private-key",
                    "capabilities": {},
                    "public_key": "test input containing PRIVATE KEY material",
                },
            )

            assert oversized.status_code == 422
            assert oversized.json()["error"]["code"] == "INVALID_DEVICE_DATA"
            assert private_key.status_code == 422
            assert private_key.json()["error"]["code"] == "INVALID_DEVICE_DATA"

    asyncio.run(scenario())
