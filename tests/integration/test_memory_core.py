"""Memory lifecycle, deduplication, history, expiration, retrieval, and audit tests."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update

from backend.app.audit.engine import AuditEngine
from backend.app.audit.models import AuditEvent
from backend.app.identity.context import AuthenticationLevel, IdentityContext
from backend.app.memory.enums import MemoryClass, MemoryEventType, MemorySourceType, MemoryStatus
from backend.app.memory.models import MemoryEvent, MemoryRecord, MemoryRevision
from backend.app.memory.schemas import MemoryProposal
from backend.app.memory.service import MemoryService
from backend.app.permissions.engine import PermissionsEngine
from backend.app.permissions.enums import AuditEventType
from tests.helpers import api_client, bearer, make_claims
from tests.phase2_helpers import scope
from tests.phase3_helpers import task_payload
from tests.phase4_helpers import grant_memory_permissions, memory_payload


def test_explicit_memory_deduplicates_but_historical_decisions_remain_distinct() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-dedup", aal="aal2")
        async with api_client({"owner": claims}) as (client, database, _):
            await grant_memory_permissions(client, "owner")
            first = await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload("I prefer concise responses"),
            )
            duplicate = await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload("  I PREFER  concise responses  ", subject="INTERACTION"),
            )
            decision_payload = memory_payload(
                "Use PostgreSQL",
                memory_class="HISTORICAL_DECISION",
                subject="architecture",
            )
            decision_one = await client.post(
                "/api/v1/memories", headers=bearer("owner"), json=decision_payload
            )
            decision_two = await client.post(
                "/api/v1/memories", headers=bearer("owner"), json=decision_payload
            )

            assert first.status_code == duplicate.status_code == 201
            assert first.json()["id"] == duplicate.json()["id"]
            assert first.json()["source_type"] == "USER_EXPLICIT"
            assert first.json()["confidence"] == 100
            assert "fingerprint" not in first.json()
            assert decision_one.json()["id"] != decision_two.json()["id"]

            memory_id = UUID(first.json()["id"])
            async with database.session_factory() as session:
                count = await session.scalar(select(func.count()).select_from(MemoryRecord))
                events = list(
                    await session.scalars(
                        select(MemoryEvent).where(MemoryEvent.memory_id == memory_id)
                    )
                )
                assert count == 3
                assert {event.event_type for event in events} == {
                    MemoryEventType.CREATED,
                    MemoryEventType.DEDUPLICATED,
                }

    asyncio.run(scenario())


def test_update_is_versioned_and_preserves_reconstructable_revision() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-update", aal="aal2")
        async with api_client({"owner": claims}) as (client, _, _):
            await grant_memory_permissions(client, "owner")
            created = await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload("I prefer detailed responses"),
            )
            memory_id = created.json()["id"]
            changed = await client.patch(
                f"/api/v1/memories/{memory_id}",
                headers=bearer("owner"),
                json={
                    "expected_version": 1,
                    "content": "I prefer concise responses",
                    "importance": 90,
                },
            )
            stale = await client.patch(
                f"/api/v1/memories/{memory_id}",
                headers=bearer("owner"),
                json={"expected_version": 1, "content": "stale overwrite"},
            )
            history = await client.get(
                f"/api/v1/memories/{memory_id}/revisions", headers=bearer("owner")
            )
            assert changed.status_code == 200
            assert changed.json()["version"] == 2
            assert changed.json()["importance"] == 90
            assert stale.status_code == 409
            assert stale.json()["error"]["code"] == "MEMORY_CONCURRENT_MODIFICATION"
            assert history.status_code == 200
            assert history.json()[0]["content"] == "I prefer detailed responses"
            assert history.json()[0]["revision_number"] == 1

    asyncio.run(scenario())


def test_same_canonical_memory_is_independent_between_users() -> None:
    async def scenario() -> None:
        claims_a = make_claims(session_id="memory-dedup-user-a", aal="aal2")
        claims_b = make_claims(session_id="memory-dedup-user-b", aal="aal2")
        async with api_client({"a": claims_a, "b": claims_b}) as (client, _, _):
            await grant_memory_permissions(client, "a")
            await grant_memory_permissions(client, "b")
            payload = memory_payload("Shared wording, separate ownership")
            first = await client.post("/api/v1/memories", headers=bearer("a"), json=payload)
            second = await client.post("/api/v1/memories", headers=bearer("b"), json=payload)
            assert first.status_code == second.status_code == 201
            assert first.json()["id"] != second.json()["id"]

    asyncio.run(scenario())


def test_historical_decision_content_cannot_be_overwritten() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-history-immutable", aal="aal2")
        async with api_client({"owner": claims}) as (client, _, _):
            await grant_memory_permissions(client, "owner")
            created = await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload(
                    "Architecture approved",
                    memory_class="HISTORICAL_DECISION",
                    subject="architecture",
                ),
            )
            response = await client.patch(
                f"/api/v1/memories/{created.json()['id']}",
                headers=bearer("owner"),
                json={"expected_version": 1, "content": "Rewritten history"},
            )
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "MEMORY_IMMUTABLE"

    asyncio.run(scenario())


def test_archive_is_idempotent_and_requires_explicit_archived_retrieval() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-archive", aal="aal2")
        async with api_client({"owner": claims}) as (client, _, _):
            await grant_memory_permissions(client, "owner")
            created = await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload("Active project state", memory_class="OPERATIONAL"),
            )
            memory_id = created.json()["id"]
            archived = await client.post(
                f"/api/v1/memories/{memory_id}/archive",
                headers=bearer("owner"),
                json={"expected_version": 1},
            )
            repeated = await client.post(
                f"/api/v1/memories/{memory_id}/archive",
                headers=bearer("owner"),
                json={"expected_version": 1},
            )
            active = await client.get("/api/v1/memories", headers=bearer("owner"))
            explicit = await client.get("/api/v1/memories?status=ARCHIVED", headers=bearer("owner"))
            direct = await client.get(f"/api/v1/memories/{memory_id}", headers=bearer("owner"))
            assert archived.json()["status"] == repeated.json()["status"] == "ARCHIVED"
            assert archived.json()["version"] == 2
            assert active.json() == []
            assert [item["id"] for item in explicit.json()] == [memory_id]
            assert direct.status_code == 404

    asyncio.run(scenario())


def test_archive_wins_over_a_stale_update_without_last_write_wins_corruption() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-archive-update-race", aal="aal2")
        async with api_client({"owner": claims}) as (client, _, _):
            await grant_memory_permissions(client, "owner")
            created = await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload("Archive race content", memory_class="OPERATIONAL"),
            )
            memory_id = created.json()["id"]
            archived = await client.post(
                f"/api/v1/memories/{memory_id}/archive",
                headers=bearer("owner"),
                json={"expected_version": 1},
            )
            stale_update = await client.patch(
                f"/api/v1/memories/{memory_id}",
                headers=bearer("owner"),
                json={"expected_version": 1, "content": "stale update"},
            )
            explicit = await client.get("/api/v1/memories?status=ARCHIVED", headers=bearer("owner"))
            assert archived.status_code == 200
            assert stale_update.status_code == 404
            assert explicit.json()[0]["content"] == "Archive race content"

    asyncio.run(scenario())


def test_privacy_delete_scrubs_current_and_revision_content_and_cannot_resurrect() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-delete", aal="aal2")
        sensitive_content = "private_key=ultra-secret-memory"
        async with api_client({"owner": claims}) as (client, database, _):
            await grant_memory_permissions(client, "owner")
            created = await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload(sensitive_content, sensitivity="CRITICAL"),
            )
            memory_id = created.json()["id"]
            changed = await client.patch(
                f"/api/v1/memories/{memory_id}",
                headers=bearer("owner"),
                json={"expected_version": 1, "summary": "critical preference"},
            )
            assert changed.status_code == 200
            deleted = await client.delete(
                f"/api/v1/memories/{memory_id}?expected_version=2",
                headers=bearer("owner"),
            )
            repeated = await client.delete(
                f"/api/v1/memories/{memory_id}?expected_version=1",
                headers=bearer("owner"),
            )
            read = await client.get(f"/api/v1/memories/{memory_id}", headers=bearer("owner"))
            resurrection = await client.patch(
                f"/api/v1/memories/{memory_id}",
                headers=bearer("owner"),
                json={"expected_version": 3, "content": "resurrected"},
            )
            assert deleted.status_code == repeated.status_code == 204
            assert read.status_code == resurrection.status_code == 404

            async with database.session_factory() as session:
                memory = await session.get(MemoryRecord, UUID(memory_id))
                revisions = list(
                    await session.scalars(
                        select(MemoryRevision).where(MemoryRevision.memory_id == UUID(memory_id))
                    )
                )
                audit = list(
                    await session.scalars(
                        select(AuditEvent).where(AuditEvent.resource_id == memory_id)
                    )
                )
                assert memory is not None
                assert memory.status is MemoryStatus.DELETED
                assert memory.content == "[DELETED]"
                assert memory.normalized_content is None
                assert all(revision.content == "[DELETED]" for revision in revisions)
                serialized_audit = json.dumps(
                    [event.metadata_payload for event in audit], sort_keys=True
                )
                assert "ultra-secret-memory" not in serialized_audit
                assert any(event.event_type is AuditEventType.MEMORY_DELETED for event in audit)

    asyncio.run(scenario())


def test_temporary_memory_expires_lazily_without_cron_and_cannot_reactivate() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-expiry", aal="aal2")
        async with api_client({"owner": claims}) as (client, database, _):
            await grant_memory_permissions(client, "owner")
            created = await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload(
                    "Short-lived context",
                    memory_class="TEMPORARY_CONTEXT",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                ),
            )
            memory_id = UUID(created.json()["id"])
            now = datetime.now(UTC)
            async with database.session_factory() as session:
                await session.execute(
                    update(MemoryRecord)
                    .where(MemoryRecord.id == memory_id)
                    .values(
                        created_at=now - timedelta(hours=2), expires_at=now - timedelta(hours=1)
                    )
                )
                await session.commit()

            direct = await client.get(f"/api/v1/memories/{memory_id}", headers=bearer("owner"))
            expired = await client.get("/api/v1/memories?status=EXPIRED", headers=bearer("owner"))
            update_response = await client.patch(
                f"/api/v1/memories/{memory_id}",
                headers=bearer("owner"),
                json={"expected_version": 2, "content": "revived"},
            )
            assert direct.status_code == 404
            assert expired.json()[0]["status"] == "EXPIRED"
            assert expired.json()[0]["version"] == 2
            assert update_response.status_code == 404

    asyncio.run(scenario())


def test_retrieval_filters_are_bounded_and_discardable_is_opt_in() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-retrieval", aal="aal2")
        async with api_client({"owner": claims}) as (client, _, _):
            await grant_memory_permissions(client, "owner")
            await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload(
                    "Critical project constraint",
                    memory_class="OPERATIONAL",
                    subject="project",
                    importance=95,
                ),
            )
            await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload(
                    "Low-value noise",
                    memory_class="DISCARDABLE",
                    subject="noise",
                    importance=5,
                ),
            )
            default = await client.get("/api/v1/memories", headers=bearer("owner"))
            filtered = await client.get(
                "/api/v1/memories?memory_class=OPERATIONAL&min_importance=90&limit=1",
                headers=bearer("owner"),
            )
            discardable = await client.get(
                "/api/v1/memories?memory_class=DISCARDABLE", headers=bearer("owner")
            )
            too_large = await client.get("/api/v1/memories?limit=101", headers=bearer("owner"))
            assert len(default.json()) == 1
            assert filtered.json()[0]["subject"] == "project"
            assert discardable.json()[0]["memory_class"] == "DISCARDABLE"
            assert too_large.status_code == 422

    asyncio.run(scenario())


def test_context_pack_is_deterministic_bounded_and_excludes_discardable() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-context-pack", aal="aal2")
        async with api_client({"owner": claims}) as (client, database, _):
            await grant_memory_permissions(client, "owner")
            me = await client.get("/api/v1/me", headers=bearer("owner"))
            for index in range(7):
                await client.post(
                    "/api/v1/memories",
                    headers=bearer("owner"),
                    json=memory_payload(
                        f"Preference {index}",
                        subject=f"preference-{index}",
                        importance=50 + index,
                    ),
                )
            await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload("Noise", memory_class="DISCARDABLE", subject="noise"),
            )
            identity = IdentityContext(
                user_id=UUID(me.json()["user_id"]),
                auth_user_id=claims.sub,
                device_id=None,
                session_id=None,
                display_name=me.json()["display_name"],
                authentication_level=AuthenticationLevel.AAL2,
                token_expiry=datetime.fromtimestamp(claims.exp, UTC),
            )
            async with database.session_factory() as session:
                audit = AuditEngine(session)
                service = MemoryService(session, PermissionsEngine(session, audit), audit)
                result = await service.build_context_pack(identity)
                assert result.value is not None
                assert len(result.value.persistent_preferences) == 5
                assert result.value.persistent_preferences[0].importance == 56
                assert all(item.subject != "noise" for item in result.value.persistent_preferences)

    asyncio.run(scenario())


def test_internal_task_provenance_is_owned_and_future_ai_proposal_cannot_persist() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-task-source", aal="aal2")
        async with api_client({"owner": claims}) as (client, database, _):
            await grant_memory_permissions(client, "owner")
            me = await client.get("/api/v1/me", headers=bearer("owner"))
            task = await client.post(
                "/api/v1/tasks",
                headers=bearer("owner"),
                json=task_payload(
                    "device.read",
                    "read",
                    scope("device", "read"),
                    "memory-task-source-001",
                ),
            )
            identity = IdentityContext(
                user_id=UUID(me.json()["user_id"]),
                auth_user_id=claims.sub,
                device_id=None,
                session_id=None,
                display_name=me.json()["display_name"],
                authentication_level=AuthenticationLevel.AAL2,
                token_expiry=datetime.fromtimestamp(claims.exp, UTC),
            )
            async with database.session_factory() as session:
                audit = AuditEngine(session)
                service = MemoryService(session, PermissionsEngine(session, audit), audit)
                task_proposal = MemoryProposal(
                    memory_class=MemoryClass.OPERATIONAL,
                    content="Task is waiting for permission",
                    source_type=MemorySourceType.TASK,
                    source_reference=task.json()["id"],
                    confidence=100,
                )
                stored = await service.create_internal(identity, task_proposal)
                assert stored.value is not None
                assert stored.value.source_type is MemorySourceType.TASK
                invalid_ai = MemoryProposal(
                    memory_class=MemoryClass.OPERATIONAL,
                    content="Untrusted inference",
                    source_type=MemorySourceType.FUTURE_AI_PROPOSAL,
                    confidence=50,
                )
                try:
                    await service.create_internal(identity, invalid_ai)
                except Exception as error:
                    assert getattr(error, "code", None) == "INVALID_MEMORY_DATA"
                else:
                    raise AssertionError("An AI proposal persisted without a policy boundary")

    asyncio.run(scenario())
