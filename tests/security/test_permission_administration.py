"""Permission bootstrap, IDOR, escalation, and revocation security tests."""

import asyncio
from uuid import uuid4

from sqlalchemy import func, select

from backend.app.audit.models import AuditEvent
from backend.app.permissions.enums import AuditEventType
from tests.helpers import api_client, bearer, make_claims
from tests.phase2_helpers import grant_payload, proposal, scope


def test_permission_grant_requires_aal2_account_control() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="grant-aal1", aal="aal1")
        async with api_client({"owner": claims}) as (client, _, _):
            response = await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("device.read", scope("device", "read", ["primary"])),
            )
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "STEP_UP_AUTHENTICATION_REQUIRED"

    asyncio.run(scenario())


def test_repeated_identical_grant_is_idempotent_and_server_sourced() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="grant-idempotent", aal="aal2")
        payload = grant_payload("device.read", scope("device", "read", ["primary"]))
        async with api_client({"owner": claims}) as (client, _, _):
            first = await client.post(
                "/api/v1/permissions/grant", headers=bearer("owner"), json=payload
            )
            second = await client.post(
                "/api/v1/permissions/grant", headers=bearer("owner"), json=payload
            )

            assert first.status_code == 200
            assert first.json()["id"] == second.json()["id"]
            assert first.json()["grant_source"] == "USER_EXPLICIT"

    asyncio.run(scenario())


def test_client_cannot_supply_owner_grant_source_or_authority_flags() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="grant-escalation", aal="aal2")
        payload = grant_payload("device.read", scope("device", "read", ["primary"]))
        payload.update(
            {
                "user_id": str(uuid4()),
                "grant_source": "LLM_GRANTED",
                "permission_granted": True,
            }
        )
        async with api_client({"owner": claims}) as (client, _, _):
            response = await client.post(
                "/api/v1/permissions/grant", headers=bearer("owner"), json=payload
            )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "INVALID_PERMISSION_DATA"

    asyncio.run(scenario())


def test_permission_endpoints_enforce_cross_user_isolation() -> None:
    async def scenario() -> None:
        claims_a = make_claims(session_id="permission-idor-a", aal="aal2")
        claims_b = make_claims(session_id="permission-idor-b", aal="aal2")
        async with api_client({"a": claims_a, "b": claims_b}) as (client, _, _):
            granted_b = await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("b"),
                json=grant_payload("device.read", scope("device", "read", ["b-device"])),
            )
            permission_id = granted_b.json()["id"]
            get_attempt = await client.get(
                f"/api/v1/permissions/{permission_id}", headers=bearer("a")
            )
            revoke_attempt = await client.post(
                f"/api/v1/permissions/{permission_id}/revoke", headers=bearer("a")
            )
            list_a = await client.get("/api/v1/permissions", headers=bearer("a"))
            list_b = await client.get("/api/v1/permissions", headers=bearer("b"))

            assert get_attempt.status_code == 404
            assert revoke_attempt.status_code == 404
            assert list_a.json() == []
            assert [item["id"] for item in list_b.json()] == [permission_id]

    asyncio.run(scenario())


def test_revocation_is_immediate_idempotent_and_audited_once() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="permission-revoke", aal="aal2")
        request_scope = scope("device", "read", ["primary"])
        async with api_client({"owner": claims}) as (client, database, _):
            granted = await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("device.read", request_scope),
            )
            permission_id = granted.json()["id"]
            first = await client.post(
                f"/api/v1/permissions/{permission_id}/revoke", headers=bearer("owner")
            )
            second = await client.post(
                f"/api/v1/permissions/{permission_id}/revoke", headers=bearer("owner")
            )
            denied = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.read", "read", request_scope),
            )

            assert first.json()["status"] == "REVOKED"
            assert second.json()["status"] == "REVOKED"
            assert first.json()["revoked_at"] == second.json()["revoked_at"]
            assert denied.json()["decision"] == "DENY"
            async with database.session_factory() as session:
                count = await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.event_type == AuditEventType.PERMISSION_REVOKED)
                )
                assert count == 1

    asyncio.run(scenario())


def test_capability_spoofing_and_sensitive_context_fail_closed() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="capability-spoof", aal="aal2")
        request_scope = scope("device", "read", ["primary"])
        async with api_client({"owner": claims}) as (client, _, _):
            unknown = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("unknown.execute", "read", request_scope),
            )
            sensitive = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal(
                    "device.read",
                    "read",
                    request_scope,
                    context={"access_token": "must-not-be-accepted"},
                ),
            )

            assert unknown.status_code == 200
            assert unknown.json()["decision"] == "DENY"
            assert unknown.json()["reason_codes"] == ["CAPABILITY_NOT_FOUND"]
            assert sensitive.status_code == 422
            assert "must-not-be-accepted" not in sensitive.text

    asyncio.run(scenario())
