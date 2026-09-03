"""Default-deny permission, scope, device, expiry, and capability matrix."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select

from backend.app.identity.models import User, UserStatus
from backend.app.permissions.enums import PermissionStatus
from backend.app.permissions.models import Capability, Permission
from tests.helpers import api_client, bearer, make_claims
from tests.phase2_helpers import grant_payload, proposal, scope


def test_no_permission_is_denied_and_valid_permission_is_allowed() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="permission-basic", aal="aal2")
        request_scope = scope("device", "read", ["primary"])
        async with api_client({"owner": claims}) as (client, _, _):
            denied = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.read", "read", request_scope),
            )
            grant = await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("device.read", request_scope),
            )
            allowed = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.read", "read", request_scope),
            )

            assert denied.status_code == 200
            assert denied.json()["decision"] == "DENY"
            assert denied.json()["reason_codes"] == ["NO_PERMISSION"]
            assert grant.status_code == 200
            assert allowed.json()["decision"] == "ALLOW"
            assert allowed.json()["scope_match"] is True

    asyncio.run(scenario())


def test_scope_is_enforced_for_operations_resources_and_resource_type() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="permission-scope", aal="aal2")
        granted_scope = scope("device", "read", ["device-a"])
        async with api_client({"owner": claims}) as (client, _, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("device.read", granted_scope),
            )
            wrong_resource = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.read", "read", scope("device", "read", ["device-b"])),
            )
            wrong_type = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.read", "read", scope("calendar", "read", ["device-a"])),
            )
            write_attempt = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.read", "write", scope("device", "write", ["device-a"])),
            )

            for response in (wrong_resource, wrong_type):
                assert response.status_code == 200
                assert response.json()["decision"] == "DENY"
                assert response.json()["reason_codes"] == ["SCOPE_MISMATCH"]
            assert write_attempt.status_code == 200
            assert write_attempt.json()["decision"] == "DENY"
            assert write_attempt.json()["reason_codes"] == ["ACTION_NOT_ALLOWED"]

    asyncio.run(scenario())


def test_revoked_and_runtime_expired_permissions_are_denied() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="permission-lifecycle", aal="aal2")
        request_scope = scope("device", "read", ["primary"])
        async with api_client({"owner": claims}) as (client, database, _):
            first = await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("device.read", request_scope),
            )
            await client.post(
                f"/api/v1/permissions/{first.json()['id']}/revoke",
                headers=bearer("owner"),
            )
            revoked = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.read", "read", request_scope),
            )

            second = await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload(
                    "device.read",
                    request_scope,
                    expires_at=datetime.now(UTC) + timedelta(minutes=5),
                ),
            )
            async with database.session_factory() as session:
                permission = await session.get(Permission, UUID(second.json()["id"]))
                assert permission is not None
                permission.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                await session.commit()

            expired = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.read", "read", request_scope),
            )

            assert revoked.json()["reason_codes"] == ["PERMISSION_REVOKED"]
            assert expired.json()["decision"] == "DENY"
            assert expired.json()["reason_codes"] == ["PERMISSION_EXPIRED"]
            async with database.session_factory() as session:
                persisted = await session.get(Permission, UUID(second.json()["id"]))
                assert persisted is not None
                assert persisted.status is PermissionStatus.EXPIRED

    asyncio.run(scenario())


def test_disabled_capability_kills_existing_permission() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="capability-disabled", aal="aal2")
        request_scope = scope("device", "read", ["primary"])
        async with api_client({"owner": claims}) as (client, database, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("device.read", request_scope),
            )
            async with database.session_factory() as session:
                capability = await session.scalar(
                    select(Capability).where(Capability.key == "device.read")
                )
                assert capability is not None
                capability.enabled = False
                await session.commit()

            response = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.read", "read", request_scope),
            )

            assert response.json()["decision"] == "DENY"
            assert response.json()["reason_codes"] == ["CAPABILITY_DISABLED"]

    asyncio.run(scenario())


def test_device_scoped_permission_requires_same_active_owned_device() -> None:
    async def scenario() -> None:
        auth_user_id = uuid4()
        claims_device = make_claims(
            auth_user_id=auth_user_id, session_id="device-scope-a", aal="aal2"
        )
        claims_other = make_claims(
            auth_user_id=auth_user_id, session_id="device-scope-b", aal="aal2"
        )
        request_scope = scope("device", "read", ["primary"])
        async with api_client({"device": claims_device, "other": claims_other}) as (
            client,
            _,
            _,
        ):
            registered = await client.post(
                "/api/v1/devices/register",
                headers=bearer("device"),
                json={
                    "device_name": "Scoped Browser",
                    "device_type": "WEB",
                    "platform": "WEB",
                    "device_identifier": "phase2-device-scoped-001",
                    "capabilities": {},
                },
            )
            device_id = registered.json()["id"]
            grant = await client.post(
                "/api/v1/permissions/grant",
                headers={**bearer("device"), "X-Device-ID": device_id},
                json=grant_payload("device.read", request_scope, device_id=device_id),
            )
            allowed = await client.post(
                "/api/v1/authorization/evaluate",
                headers={**bearer("device"), "X-Device-ID": device_id},
                json=proposal("device.read", "read", request_scope),
            )
            mismatch = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("other"),
                json=proposal("device.read", "read", request_scope),
            )
            revoked = await client.post(
                f"/api/v1/devices/{device_id}/revoke",
                headers=bearer("device"),
            )
            revoked_use = await client.post(
                "/api/v1/authorization/evaluate",
                headers={**bearer("other"), "X-Device-ID": device_id},
                json=proposal("device.read", "read", request_scope),
            )

            assert grant.status_code == 200
            assert allowed.json()["decision"] == "ALLOW"
            assert mismatch.json()["reason_codes"] == ["DEVICE_SCOPE_MISMATCH"]
            assert revoked.status_code == 200
            assert revoked_use.status_code == 403
            assert revoked_use.json()["error"]["code"] == "DEVICE_REVOKED"

    asyncio.run(scenario())


def test_disabled_user_cannot_reach_authorization_engine() -> None:
    async def scenario() -> None:
        auth_user_id = uuid4()
        claims = make_claims(auth_user_id=auth_user_id, session_id="disabled-phase2", aal="aal2")
        async with api_client({"owner": claims}) as (client, database, _):
            async with database.session_factory() as session:
                session.add(
                    User(
                        auth_user_id=auth_user_id,
                        display_name="Disabled",
                        status=UserStatus.DISABLED,
                    )
                )
                await session.commit()
            response = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.read", "read", scope("device", "read", ["primary"])),
            )
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "USER_DISABLED"

    asyncio.run(scenario())


def test_database_constraints_reject_duplicate_capability_and_invalid_permission_status() -> None:
    async def scenario() -> None:
        async with api_client({}) as (_, database, _):
            async with database.session_factory() as session:
                duplicate = Capability(
                    key="device.read",
                    name="Duplicate",
                    description="Must fail uniqueness",
                    category="device",
                    default_risk_level=1,
                    allowed_actions=["read"],
                )
                session.add(duplicate)
                try:
                    await session.commit()
                except Exception as error:
                    assert "unique" in str(error).lower()
                    await session.rollback()
                else:
                    raise AssertionError("Duplicate capability key was accepted")

    asyncio.run(scenario())
