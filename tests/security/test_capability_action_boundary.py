"""Capability/action authority matrix at grant and authorization boundaries."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import select

from backend.app.identity.models import User, utc_now
from backend.app.permissions.enums import (
    ConfirmationPolicy,
    PermissionGrantSource,
    PermissionStatus,
)
from backend.app.permissions.models import Capability, Permission
from backend.app.permissions.schemas import PermissionScope
from tests.helpers import api_client, bearer, make_claims
from tests.phase2_helpers import grant_payload, proposal, scope


@pytest.mark.parametrize(
    ("capability_key", "action", "resource_type"),
    [
        ("device.read", "read", "device"),
        ("device.manage", "revoke", "device"),
        ("notification.send", "send", "notification"),
        ("data.delete", "delete", "data"),
        ("finance.read", "read", "finance"),
    ],
)
def test_server_defined_capability_action_pairs_can_be_granted_and_authorized(
    capability_key: str,
    action: str,
    resource_type: str,
) -> None:
    async def scenario() -> None:
        claims = make_claims(session_id=f"valid-{capability_key}-{action}", aal="aal2")
        request_scope = scope(resource_type, action, ["owned-resource"])
        async with api_client({"owner": claims}) as (client, _, _):
            grant = await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload(capability_key, request_scope),
            )
            authorization = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal(capability_key, action, request_scope),
            )

            assert grant.status_code == 200
            assert action in grant.json()["capability"]["allowed_actions"]
            assert authorization.status_code == 200
            assert authorization.json()["decision"] == "ALLOW"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("capability_key", "action", "resource_type"),
    [
        ("device.read", "write", "device"),
        ("device.read", "delete", "device"),
        ("notification.send", "delete", "notification"),
        ("finance.read", "buy", "finance"),
        ("device.manage", "invented", "device"),
    ],
)
def test_unsupported_actions_are_rejected_at_grant_and_denied_at_authorization(
    capability_key: str,
    action: str,
    resource_type: str,
) -> None:
    async def scenario() -> None:
        claims = make_claims(session_id=f"invalid-{capability_key}-{action}", aal="aal2")
        request_scope = scope(resource_type, action, ["owned-resource"])
        async with api_client({"owner": claims}) as (client, _, _):
            grant = await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload(capability_key, request_scope),
            )
            authorization = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal(capability_key, action, request_scope),
            )

            assert grant.status_code == 422
            assert grant.json()["error"]["code"] == "ACTION_NOT_ALLOWED"
            assert authorization.status_code == 200
            assert authorization.json()["decision"] == "DENY"
            assert authorization.json()["reason_codes"] == ["ACTION_NOT_ALLOWED"]
            assert authorization.json()["permission_id"] is None

    asyncio.run(scenario())


def test_finance_execute_valid_action_remains_blocked_by_financial_guard() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="valid-finance-action-guarded", aal="aal2")
        request_scope = scope("finance", "buy", ["account-a"])
        async with api_client({"owner": claims}) as (client, _, _):
            grant = await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("finance.execute", request_scope),
            )
            authorization = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("finance.execute", "buy", request_scope),
            )

            assert grant.status_code == 200
            assert authorization.json()["decision"] == "DENY"
            assert authorization.json()["reason_codes"] == ["FINANCIAL_EXECUTION_BLOCKED"]
            assert authorization.json()["financial_guard_triggered"] is True

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("legacy_operations", "requested_action"),
    [
        (["delete"], "delete"),
        (["delete", "read"], "read"),
    ],
)
def test_malformed_legacy_permission_cannot_bypass_authorization_defense(
    legacy_operations: list[str], requested_action: str
) -> None:
    async def scenario() -> None:
        claims = make_claims(session_id=f"legacy-{requested_action}", aal="aal2")
        async with api_client({"owner": claims}) as (client, database, _):
            me = await client.get("/api/v1/me", headers=bearer("owner"))
            user_id = UUID(me.json()["user_id"])
            legacy_scope = PermissionScope(
                resource_type="device",
                resource_ids=["owned-device"],
                operations=legacy_operations,
            )
            async with database.session_factory() as session:
                user = await session.get(User, user_id)
                capability = await session.scalar(
                    select(Capability).where(Capability.key == "device.read")
                )
                assert user is not None
                assert capability is not None
                session.add(
                    Permission(
                        user_id=user.id,
                        capability_id=capability.id,
                        scope=legacy_scope.model_dump(mode="json"),
                        scope_digest=legacy_scope.digest,
                        status=PermissionStatus.ACTIVE,
                        confirmation_policy=ConfirmationPolicy.NEVER,
                        auto_execute=False,
                        grant_source=PermissionGrantSource.MIGRATION,
                        granted_at=utc_now(),
                    )
                )
                await session.commit()

            requested_scope = scope("device", requested_action, ["owned-device"])
            authorization = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.read", requested_action, requested_scope),
            )

            assert authorization.status_code == 200
            assert authorization.json()["decision"] == "DENY"
            assert authorization.json()["reason_codes"] == ["ACTION_NOT_ALLOWED"]
            assert authorization.json()["financial_guard_triggered"] is False

    asyncio.run(scenario())
