"""Human confirmation binding, expiry, isolation, and replay tests."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from backend.app.permissions.models import ConfirmationRequest
from tests.helpers import api_client, bearer, make_claims
from tests.phase2_helpers import grant_payload, proposal, scope


def test_every_time_confirmation_is_action_bound_and_single_use() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="confirm-every-time", aal="aal2")
        request_scope = scope("notification", "send", ["primary"])
        async with api_client({"owner": claims}) as (client, _, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("notification.send", request_scope, policy="EVERY_TIME"),
            )
            first = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("notification.send", "send", request_scope),
            )
            confirmation_id = first.json()["confirmation_id"]
            approved = await client.post(
                f"/api/v1/confirmations/{confirmation_id}/approve",
                headers=bearer("owner"),
            )
            consumed = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal(
                    "notification.send",
                    "send",
                    request_scope,
                    confirmation_id=confirmation_id,
                ),
            )
            replay = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal(
                    "notification.send",
                    "send",
                    request_scope,
                    confirmation_id=confirmation_id,
                ),
            )

            assert first.json()["decision"] == "REQUIRE_CONFIRMATION"
            assert approved.json()["status"] == "APPROVED"
            assert consumed.json()["decision"] == "ALLOW"
            assert replay.json()["decision"] == "DENY"
            assert replay.json()["reason_codes"] == ["CONFIRMATION_REPLAYED"]

    asyncio.run(scenario())


def test_rejected_and_expired_confirmations_cannot_authorize() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="confirm-negative", aal="aal2")
        request_scope = scope("notification", "send", ["primary"])
        async with api_client({"owner": claims}) as (client, database, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("notification.send", request_scope, policy="EVERY_TIME"),
            )
            rejected_request = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("notification.send", "send", request_scope),
            )
            rejected_id = rejected_request.json()["confirmation_id"]
            await client.post(
                f"/api/v1/confirmations/{rejected_id}/reject",
                headers=bearer("owner"),
            )
            rejected = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal(
                    "notification.send",
                    "send",
                    request_scope,
                    confirmation_id=rejected_id,
                ),
            )

            expiring_request = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("notification.send", "send", request_scope),
            )
            expiring_id = UUID(expiring_request.json()["confirmation_id"])
            await client.post(
                f"/api/v1/confirmations/{expiring_id}/approve",
                headers=bearer("owner"),
            )
            async with database.session_factory() as session:
                confirmation = await session.get(ConfirmationRequest, expiring_id)
                assert confirmation is not None
                confirmation.requested_at = datetime.now(UTC) - timedelta(minutes=10)
                confirmation.expires_at = datetime.now(UTC) - timedelta(minutes=5)
                await session.commit()
            expired = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal(
                    "notification.send",
                    "send",
                    request_scope,
                    confirmation_id=expiring_id,
                ),
            )

            assert rejected.json()["reason_codes"] == ["CONFIRMATION_REJECTED"]
            assert expired.json()["decision"] == "DENY"
            assert expired.json()["reason_codes"] == ["CONFIRMATION_EXPIRED"]

    asyncio.run(scenario())


def test_confirmation_cannot_be_approved_by_another_user() -> None:
    async def scenario() -> None:
        claims_a = make_claims(session_id="confirm-owner-a", aal="aal2")
        claims_b = make_claims(session_id="confirm-owner-b", aal="aal2")
        request_scope = scope("notification", "send", ["primary"])
        async with api_client({"a": claims_a, "b": claims_b}) as (client, _, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("a"),
                json=grant_payload("notification.send", request_scope, policy="EVERY_TIME"),
            )
            decision = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("a"),
                json=proposal("notification.send", "send", request_scope),
            )
            response = await client.post(
                f"/api/v1/confirmations/{decision.json()['confirmation_id']}/approve",
                headers=bearer("b"),
            )

            assert response.status_code == 404
            assert response.json()["error"]["code"] == "CONFIRMATION_NOT_FOUND"

    asyncio.run(scenario())


def test_confirmation_approval_requires_aal2() -> None:
    async def scenario() -> None:
        auth_user_id = uuid4()
        strong = make_claims(auth_user_id=auth_user_id, session_id="confirm-aal2", aal="aal2")
        weak = make_claims(auth_user_id=auth_user_id, session_id="confirm-aal1", aal="aal1")
        request_scope = scope("notification", "send", ["primary"])
        async with api_client({"strong": strong, "weak": weak}) as (client, _, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("strong"),
                json=grant_payload("notification.send", request_scope, policy="EVERY_TIME"),
            )
            decision = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("strong"),
                json=proposal("notification.send", "send", request_scope),
            )
            response = await client.post(
                f"/api/v1/confirmations/{decision.json()['confirmation_id']}/approve",
                headers=bearer("weak"),
            )

            assert response.status_code == 403
            assert response.json()["error"]["code"] == "STEP_UP_AUTHENTICATION_REQUIRED"

    asyncio.run(scenario())


def test_approval_for_action_a_cannot_authorize_action_b() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="confirm-action-binding", aal="aal2")
        granted_scope = scope("device", "register", ["primary"], additional_operations=["update"])
        register_scope = scope("device", "register", ["primary"])
        update_scope = scope("device", "update", ["primary"])
        async with api_client({"owner": claims}) as (client, _, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("device.manage", granted_scope, policy="EVERY_TIME"),
            )
            decision = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.manage", "register", register_scope),
            )
            confirmation_id = decision.json()["confirmation_id"]
            await client.post(
                f"/api/v1/confirmations/{confirmation_id}/approve",
                headers=bearer("owner"),
            )
            mismatch = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal(
                    "device.manage",
                    "update",
                    update_scope,
                    confirmation_id=confirmation_id,
                ),
            )

            assert mismatch.json()["decision"] == "DENY"
            assert mismatch.json()["reason_codes"] == ["CONFIRMATION_MISMATCH"]

    asyncio.run(scenario())


def test_once_and_high_risk_only_policies_have_distinct_semantics() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="confirm-policies", aal="aal2")
        read_scope = scope("device", "read", ["primary"])
        notify_scope = scope("notification", "send", ["primary"])
        delete_scope = scope("data", "delete", ["record-a"])
        async with api_client({"owner": claims}) as (client, _, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("device.read", read_scope, policy="ONCE"),
            )
            once_first = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.read", "read", read_scope),
            )
            await client.post(
                f"/api/v1/confirmations/{once_first.json()['confirmation_id']}/approve",
                headers=bearer("owner"),
            )
            once_after = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.read", "read", read_scope),
            )

            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("notification.send", notify_scope, policy="HIGH_RISK_ONLY"),
            )
            elevated = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("notification.send", "send", notify_scope),
            )

            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("data.delete", delete_scope, policy="HIGH_RISK_ONLY"),
            )
            high = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("data.delete", "delete", delete_scope),
            )

            assert once_first.json()["decision"] == "REQUIRE_CONFIRMATION"
            assert once_after.json()["decision"] == "ALLOW"
            assert elevated.json()["risk_level"] == 3
            assert elevated.json()["decision"] == "ALLOW"
            assert high.json()["risk_level"] == 4
            assert high.json()["decision"] == "REQUIRE_CONFIRMATION"

    asyncio.run(scenario())


def test_auto_execute_does_not_bypass_every_time_confirmation() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="confirm-auto-execute", aal="aal2")
        request_scope = scope("notification", "send", ["primary"])
        async with api_client({"owner": claims}) as (client, _, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload(
                    "notification.send",
                    request_scope,
                    policy="EVERY_TIME",
                    auto_execute=True,
                ),
            )
            response = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("notification.send", "send", request_scope),
            )
            assert response.json()["decision"] == "REQUIRE_CONFIRMATION"

    asyncio.run(scenario())
