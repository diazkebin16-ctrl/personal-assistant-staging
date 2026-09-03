"""JIT user provisioning and owned-device API integration tests."""

import asyncio
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from backend.app.identity.models import Device, User, UserStatus
from tests.helpers import api_client, bearer, make_claims


def registration(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "device_name": "Primary Browser",
        "device_type": "WEB",
        "platform": "WEB",
        "device_identifier": "installation-primary-001",
        "capabilities": {"notifications": True},
    }
    data.update(overrides)
    return data


def test_first_login_provisions_once_and_returns_safe_identity() -> None:
    async def scenario() -> None:
        auth_user_id = uuid4()
        claims = make_claims(
            auth_user_id=auth_user_id,
            session_id="session-provisioning",
            display_name="  Test   Person  ",
        )
        async with api_client({"user-a": claims}) as (client, database, _):
            first = await client.get("/api/v1/me", headers=bearer("user-a"))
            second = await client.get("/api/v1/me", headers=bearer("user-a"))

            assert first.status_code == 200
            assert second.status_code == 200
            assert first.json()["display_name"] == "Test Person"
            assert first.json()["authenticated"] is True
            assert "token" not in first.text.lower()

            async with database.session_factory() as session:
                count = await session.scalar(
                    select(func.count()).select_from(User).where(User.auth_user_id == auth_user_id)
                )
                assert count == 1

    asyncio.run(scenario())


def test_disabled_user_is_rejected() -> None:
    async def scenario() -> None:
        auth_user_id = uuid4()
        claims = make_claims(auth_user_id=auth_user_id, session_id="disabled-session")
        async with api_client({"disabled": claims}) as (client, database, _):
            async with database.session_factory() as session:
                session.add(
                    User(
                        auth_user_id=auth_user_id,
                        display_name="Disabled",
                        status=UserStatus.DISABLED,
                    )
                )
                await session.commit()

            response = await client.get("/api/v1/me", headers=bearer("disabled"))

            assert response.status_code == 403
            assert response.json()["error"]["code"] == "USER_DISABLED"

    asyncio.run(scenario())


def test_device_registration_is_idempotent_and_updates_allowed_metadata() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="device-session")
        async with api_client({"user-a": claims}) as (client, database, _):
            first = await client.post(
                "/api/v1/devices/register",
                headers=bearer("user-a"),
                json=registration(),
            )
            second = await client.post(
                "/api/v1/devices/register",
                headers=bearer("user-a"),
                json=registration(
                    device_name="Renamed Browser",
                    capabilities={"notifications": False, "voice_input": True},
                ),
            )

            assert first.status_code == 200
            assert second.status_code == 200
            assert first.json()["id"] == second.json()["id"]
            assert second.json()["device_name"] == "Renamed Browser"
            assert second.json()["capabilities"]["voice_input"] is True

            async with database.session_factory() as session:
                count = await session.scalar(select(func.count()).select_from(Device))
                assert count == 1

    asyncio.run(scenario())


def test_device_list_is_isolated_by_authenticated_user() -> None:
    async def scenario() -> None:
        claims_a = make_claims(session_id="session-a")
        claims_b = make_claims(session_id="session-b")
        async with api_client({"user-a": claims_a, "user-b": claims_b}) as (client, _, _):
            registered_a = await client.post(
                "/api/v1/devices/register",
                headers=bearer("user-a"),
                json=registration(device_identifier="installation-user-a"),
            )
            registered_b = await client.post(
                "/api/v1/devices/register",
                headers=bearer("user-b"),
                json=registration(device_identifier="installation-user-b"),
            )
            listed = await client.get("/api/v1/devices", headers=bearer("user-a"))

            assert registered_a.status_code == 200
            assert registered_b.status_code == 200
            assert listed.status_code == 200
            assert [item["id"] for item in listed.json()] == [registered_a.json()["id"]]

    asyncio.run(scenario())


def test_user_cannot_revoke_another_users_device() -> None:
    async def scenario() -> None:
        claims_a = make_claims(session_id="revoke-a")
        claims_b = make_claims(session_id="revoke-b")
        async with api_client({"user-a": claims_a, "user-b": claims_b}) as (client, _, _):
            registered = await client.post(
                "/api/v1/devices/register",
                headers=bearer("user-b"),
                json=registration(device_identifier="installation-owned-by-b"),
            )
            device_id = registered.json()["id"]

            response = await client.post(
                f"/api/v1/devices/{device_id}/revoke",
                headers=bearer("user-a"),
            )
            owner_list = await client.get("/api/v1/devices", headers=bearer("user-b"))

            assert response.status_code == 404
            assert response.json()["error"]["code"] == "DEVICE_NOT_FOUND"
            assert owner_list.json()[0]["revoked_at"] is None

    asyncio.run(scenario())


def test_revoked_device_cannot_be_registered_again() -> None:
    async def scenario() -> None:
        auth_user_id = uuid4()
        first_claims = make_claims(auth_user_id=auth_user_id, session_id="revoke-session-1")
        second_claims = make_claims(auth_user_id=auth_user_id, session_id="revoke-session-2")
        async with api_client({"first-session": first_claims, "new-session": second_claims}) as (
            client,
            _,
            _,
        ):
            registered = await client.post(
                "/api/v1/devices/register",
                headers=bearer("first-session"),
                json=registration(device_identifier="installation-to-revoke"),
            )
            revoked = await client.post(
                f"/api/v1/devices/{registered.json()['id']}/revoke",
                headers=bearer("first-session"),
            )
            repeated = await client.post(
                "/api/v1/devices/register",
                headers=bearer("new-session"),
                json=registration(device_identifier="installation-to-revoke"),
            )

            assert revoked.status_code == 200
            assert revoked.json()["revoked_at"] is not None
            assert repeated.status_code == 403
            assert repeated.json()["error"]["code"] == "DEVICE_REVOKED"

    asyncio.run(scenario())


def test_registered_device_can_be_resolved_in_identity_context() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="identity-device-session")
        async with api_client({"user-a": claims}) as (client, _, _):
            registered = await client.post(
                "/api/v1/devices/register",
                headers=bearer("user-a"),
                json=registration(device_identifier="installation-context"),
            )
            device_id = registered.json()["id"]
            response = await client.get(
                "/api/v1/me",
                headers={**bearer("user-a"), "X-Device-ID": device_id},
            )

            assert response.status_code == 200
            assert response.json()["device_id"] == device_id

    asyncio.run(scenario())


def test_cross_user_device_header_is_not_accepted() -> None:
    async def scenario() -> None:
        claims_a = make_claims(session_id="header-a")
        claims_b = make_claims(session_id="header-b")
        async with api_client({"user-a": claims_a, "user-b": claims_b}) as (client, _, _):
            registered_b = await client.post(
                "/api/v1/devices/register",
                headers=bearer("user-b"),
                json=registration(device_identifier="installation-header-b"),
            )
            response = await client.get(
                "/api/v1/me",
                headers={
                    **bearer("user-a"),
                    "X-Device-ID": registered_b.json()["id"],
                },
            )

            assert response.status_code == 404
            assert response.json()["error"]["code"] == "DEVICE_NOT_FOUND"

    asyncio.run(scenario())
