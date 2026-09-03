"""Task Engine authority, ownership, spoofing, and hard-deny tests."""

import asyncio
from uuid import uuid4

from sqlalchemy import func, select

from backend.app.tasks.models import Task
from tests.helpers import api_client, bearer, make_claims
from tests.phase2_helpers import grant_payload, scope
from tests.phase3_helpers import task_payload


def test_cross_user_task_read_and_cancel_are_hidden() -> None:
    async def scenario() -> None:
        claims_a = make_claims(session_id="task-owner-a", aal="aal2")
        claims_b = make_claims(session_id="task-owner-b", aal="aal2")
        async with api_client({"a": claims_a, "b": claims_b}) as (client, _, _):
            created = await client.post(
                "/api/v1/tasks",
                headers=bearer("b"),
                json=task_payload(
                    "device.read", "read", scope("device", "read"), "task-owner-b-001"
                ),
            )
            task_id = created.json()["id"]
            read = await client.get(f"/api/v1/tasks/{task_id}", headers=bearer("a"))
            cancel = await client.post(
                f"/api/v1/tasks/{task_id}/cancel",
                headers=bearer("a"),
                json={"expected_version": 1},
            )
            assert read.status_code == cancel.status_code == 404

    asyncio.run(scenario())


def test_client_cannot_supply_owner_state_or_authority() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="task-spoof", aal="aal2")
        payload = task_payload("device.read", "read", scope("device", "read"), "task-spoof-001")
        payload.update(
            {
                "user_id": str(uuid4()),
                "status": "COMPLETED",
                "permission_granted": True,
                "risk_level": 0,
            }
        )
        async with api_client({"owner": claims}) as (client, _, _):
            response = await client.post("/api/v1/tasks", headers=bearer("owner"), json=payload)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "INVALID_TASK_DATA"

    asyncio.run(scenario())


def test_invalid_capability_action_and_financial_execution_are_hard_denied_without_task() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="task-hard-deny", aal="aal2")
        finance_scope = scope("finance", "buy", ["account-a"])
        async with api_client({"owner": claims}) as (client, database, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("finance.execute", finance_scope),
            )
            invalid_action = await client.post(
                "/api/v1/tasks",
                headers=bearer("owner"),
                json=task_payload(
                    "device.read",
                    "delete",
                    scope("device", "delete"),
                    "task-invalid-action-001",
                ),
            )
            financial = await client.post(
                "/api/v1/tasks",
                headers=bearer("owner"),
                json=task_payload(
                    "finance.execute", "buy", finance_scope, "task-financial-deny-001"
                ),
            )
            assert invalid_action.status_code == financial.status_code == 403
            assert financial.json()["error"]["code"] == "TASK_AUTHORIZATION_DENIED"
            async with database.session_factory() as session:
                assert await session.scalar(select(func.count()).select_from(Task)) == 0

    asyncio.run(scenario())


def test_unowned_or_revoked_device_cannot_be_bound_to_task() -> None:
    async def scenario() -> None:
        claims_a = make_claims(session_id="task-device-a", aal="aal2")
        claims_b = make_claims(session_id="task-device-b", aal="aal2")
        async with api_client({"a": claims_a, "b": claims_b}) as (client, _, _):
            registered = await client.post(
                "/api/v1/devices/register",
                headers=bearer("b"),
                json={
                    "device_name": "Other Device",
                    "device_type": "WEB",
                    "platform": "WEB",
                    "device_identifier": "task-other-device-001",
                    "capabilities": {},
                },
            )
            response = await client.post(
                "/api/v1/tasks",
                headers=bearer("a"),
                json=task_payload(
                    "device.read",
                    "read",
                    scope("device", "read"),
                    "task-device-spoof-001",
                    device_id=registered.json()["id"],
                ),
            )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "TASK_DEVICE_INVALID"

    asyncio.run(scenario())


def test_task_metadata_is_bounded_and_secret_redacted() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="task-metadata", aal="aal2")
        request_scope = scope("device", "read")
        async with api_client({"owner": claims}) as (client, _, _):
            safe = await client.post(
                "/api/v1/tasks",
                headers=bearer("owner"),
                json=task_payload(
                    "device.read",
                    "read",
                    request_scope,
                    "task-metadata-001",
                    metadata={"access_token": "must-not-leak", "label": "safe"},
                ),
            )
            oversized = await client.post(
                "/api/v1/tasks",
                headers=bearer("owner"),
                json=task_payload(
                    "device.read",
                    "read",
                    request_scope,
                    "task-metadata-002",
                    metadata={"payload": "x" * 5000},
                ),
            )
            assert safe.status_code == 200
            assert "must-not-leak" not in safe.text
            assert oversized.status_code == 422

    asyncio.run(scenario())


def test_no_public_state_or_task_event_mutation_route_exists() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="task-no-force-state", aal="aal2")
        async with api_client({"owner": claims}) as (client, _, _):
            task_id = uuid4()
            state = await client.post(
                f"/api/v1/tasks/{task_id}/state",
                headers=bearer("owner"),
                json={"status": "COMPLETED"},
            )
            event = await client.delete(
                f"/api/v1/tasks/{task_id}/events/{uuid4()}", headers=bearer("owner")
            )
            assert state.status_code == event.status_code == 404

    asyncio.run(scenario())
