"""Task creation, idempotency, lifecycle, attempts, and audit integration."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select

from backend.app.audit.engine import AuditEngine
from backend.app.audit.models import AuditEvent
from backend.app.permissions.engine import PermissionsEngine
from backend.app.permissions.enums import AuditEventType
from backend.app.tasks.enums import TaskStatus
from backend.app.tasks.models import Task, TaskAttempt, TaskEvent
from backend.app.tasks.schemas import TaskClaimRequest, TaskCompletionRequest
from backend.app.tasks.service import TaskService
from tests.helpers import api_client, bearer, make_claims
from tests.phase2_helpers import grant_payload, scope
from tests.phase3_helpers import task_payload


def test_authorized_task_is_queued_with_atomic_event_and_audit() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="task-authorized", aal="aal2")
        request_scope = scope("device", "read", ["primary"])
        async with api_client({"owner": claims}) as (client, database, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("device.read", request_scope),
            )
            response = await client.post(
                "/api/v1/tasks",
                headers=bearer("owner"),
                json=task_payload("device.read", "read", request_scope, "task-authorized-001"),
            )
            assert response.status_code == 200
            assert response.json()["status"] == "QUEUED"
            assert response.json()["version"] == 1
            task_id = UUID(response.json()["id"])
            async with database.session_factory() as session:
                event_count = await session.scalar(
                    select(func.count()).select_from(TaskEvent).where(TaskEvent.task_id == task_id)
                )
                audit_count = await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(
                        AuditEvent.task_id == task_id,
                        AuditEvent.event_type == AuditEventType.TASK_CREATED,
                    )
                )
                assert event_count == 1
                assert audit_count == 1

    asyncio.run(scenario())


def test_missing_permission_creates_resolvable_wait_state() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="task-wait-permission", aal="aal2")
        request_scope = scope("device", "read", ["primary"])
        async with api_client({"owner": claims}) as (client, _, _):
            response = await client.post(
                "/api/v1/tasks",
                headers=bearer("owner"),
                json=task_payload("device.read", "read", request_scope, "task-waiting-001"),
            )
            assert response.status_code == 200
            assert response.json()["status"] == "WAITING_PERMISSION"

    asyncio.run(scenario())


def test_confirmation_required_creates_waiting_confirmation_link() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="task-wait-confirm", aal="aal2")
        request_scope = scope("notification", "send", ["primary"])
        async with api_client({"owner": claims}) as (client, _, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("notification.send", request_scope, policy="EVERY_TIME"),
            )
            response = await client.post(
                "/api/v1/tasks",
                headers=bearer("owner"),
                json=task_payload(
                    "notification.send", "send", request_scope, "task-confirmation-001"
                ),
            )
            assert response.status_code == 200
            assert response.json()["status"] == "WAITING_CONFIRMATION"
            assert response.json()["confirmation_request_id"] is not None

    asyncio.run(scenario())


def test_idempotency_same_request_returns_same_task_and_conflicting_payload_fails() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="task-idempotency", aal="aal2")
        request_scope = scope("device", "read", ["primary"])
        first_payload = task_payload("device.read", "read", request_scope, "task-idempotency-001")
        async with api_client({"owner": claims}) as (client, database, _):
            first = await client.post("/api/v1/tasks", headers=bearer("owner"), json=first_payload)
            second = await client.post("/api/v1/tasks", headers=bearer("owner"), json=first_payload)
            changed = task_payload(
                "device.read",
                "read",
                scope("device", "read", ["different"]),
                "task-idempotency-001",
            )
            conflict = await client.post("/api/v1/tasks", headers=bearer("owner"), json=changed)

            assert first.json()["id"] == second.json()["id"]
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == "TASK_IDEMPOTENCY_CONFLICT"
            async with database.session_factory() as session:
                count = await session.scalar(select(func.count()).select_from(Task))
                assert count == 1

    asyncio.run(scenario())


def test_same_idempotency_key_is_independent_between_users() -> None:
    async def scenario() -> None:
        claims_a = make_claims(session_id="task-idem-user-a", aal="aal2")
        claims_b = make_claims(session_id="task-idem-user-b", aal="aal2")
        payload = task_payload(
            "device.read", "read", scope("device", "read"), "shared-idempotency-key"
        )
        async with api_client({"a": claims_a, "b": claims_b}) as (client, _, _):
            first = await client.post("/api/v1/tasks", headers=bearer("a"), json=payload)
            second = await client.post("/api/v1/tasks", headers=bearer("b"), json=payload)
            assert first.status_code == second.status_code == 200
            assert first.json()["id"] != second.json()["id"]

    asyncio.run(scenario())


def test_cancel_is_owned_versioned_idempotent_and_terminal() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="task-cancel", aal="aal2")
        request_scope = scope("device", "read")
        async with api_client({"owner": claims}) as (client, _, _):
            created = await client.post(
                "/api/v1/tasks",
                headers=bearer("owner"),
                json=task_payload("device.read", "read", request_scope, "task-cancel-001"),
            )
            task_id = created.json()["id"]
            first = await client.post(
                f"/api/v1/tasks/{task_id}/cancel",
                headers=bearer("owner"),
                json={"expected_version": 1},
            )
            second = await client.post(
                f"/api/v1/tasks/{task_id}/cancel",
                headers=bearer("owner"),
                json={"expected_version": 1},
            )
            assert first.json()["status"] == "CANCELLED"
            assert first.json()["version"] == 2
            assert second.json()["status"] == "CANCELLED"

    asyncio.run(scenario())


def test_stale_version_cannot_overwrite_task_state() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="task-stale-version", aal="aal2")
        async with api_client({"owner": claims}) as (client, _, _):
            created = await client.post(
                "/api/v1/tasks",
                headers=bearer("owner"),
                json=task_payload(
                    "device.read",
                    "read",
                    scope("device", "read"),
                    "task-stale-version-001",
                ),
            )
            response = await client.post(
                f"/api/v1/tasks/{created.json()['id']}/cancel",
                headers=bearer("owner"),
                json={"expected_version": 99},
            )
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "TASK_CONCURRENT_MODIFICATION"

    asyncio.run(scenario())


def test_internal_claim_is_atomic_and_preserves_attempt_history() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="task-claim", aal="aal2")
        request_scope = scope("device", "read")
        async with api_client({"owner": claims}) as (client, database, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("device.read", request_scope),
            )
            created = await client.post(
                "/api/v1/tasks",
                headers=bearer("owner"),
                json=task_payload("device.read", "read", request_scope, "task-claim-001"),
            )
            task_id = UUID(created.json()["id"])
            async with database.session_factory() as session:
                audit = AuditEngine(session)
                service = TaskService(session, PermissionsEngine(session, audit), audit)
                task, attempt = await service.claim_task(
                    task_id, TaskClaimRequest(expected_version=1, worker_id="worker-a")
                )
                assert task.status is TaskStatus.RUNNING
                assert attempt is not None
                try:
                    await service.claim_task(
                        task_id, TaskClaimRequest(expected_version=1, worker_id="worker-b")
                    )
                except Exception as error:
                    assert getattr(error, "code", None) == "TASK_NOT_CLAIMABLE"
                else:
                    raise AssertionError("A second worker claimed the same task")
                task = await service.complete_task(
                    task_id,
                    TaskCompletionRequest(expected_version=2, result_metadata={"records": 1}),
                )
                await session.commit()
                assert task.status is TaskStatus.COMPLETED
                attempts = list(
                    await session.scalars(select(TaskAttempt).where(TaskAttempt.task_id == task_id))
                )
                assert len(attempts) == 1
                assert attempts[0].status.value == "COMPLETED"

    asyncio.run(scenario())


def test_expired_task_cannot_be_claimed() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="task-expired", aal="aal2")
        request_scope = scope("device", "read")
        async with api_client({"owner": claims}) as (client, database, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("device.read", request_scope),
            )
            created = await client.post(
                "/api/v1/tasks",
                headers=bearer("owner"),
                json=task_payload(
                    "device.read",
                    "read",
                    request_scope,
                    "task-expired-001",
                    expires_at=datetime.now(UTC) + timedelta(seconds=1),
                ),
            )
            task_id = UUID(created.json()["id"])
            async with database.session_factory() as session:
                task = await session.get(Task, task_id)
                assert task is not None
                task.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                await session.commit()
            async with database.session_factory() as session:
                audit = AuditEngine(session)
                service = TaskService(session, PermissionsEngine(session, audit), audit)
                task, attempt = await service.claim_task(
                    task_id, TaskClaimRequest(expected_version=1, worker_id="worker-a")
                )
                await session.commit()
                assert task.status is TaskStatus.EXPIRED
                assert attempt is None

    asyncio.run(scenario())
