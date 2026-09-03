"""Memory ownership, spoofing, authority, confirmation, and privacy tests."""

import asyncio
from uuid import uuid4

from sqlalchemy import func, select

from backend.app.memory.models import MemoryRecord
from tests.helpers import api_client, bearer, make_claims
from tests.phase2_helpers import grant_payload, proposal, scope
from tests.phase4_helpers import grant_memory_permissions, memory_payload


def test_memory_fails_closed_without_explicit_capability_grants() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-default-deny", aal="aal2")
        async with api_client({"owner": claims}) as (client, database, _):
            create = await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload("Should not persist"),
            )
            read = await client.get("/api/v1/memories", headers=bearer("owner"))
            assert create.status_code == read.status_code == 403
            assert create.json()["error"]["code"] == "MEMORY_AUTHORIZATION_DENIED"
            async with database.session_factory() as session:
                assert await session.scalar(select(func.count()).select_from(MemoryRecord)) == 0

    asyncio.run(scenario())


def test_cross_user_memory_is_hidden_from_read_update_archive_delete_and_enumeration() -> None:
    async def scenario() -> None:
        claims_a = make_claims(session_id="memory-owner-a", aal="aal2")
        claims_b = make_claims(session_id="memory-owner-b", aal="aal2")
        async with api_client({"a": claims_a, "b": claims_b}) as (client, _, _):
            await grant_memory_permissions(client, "a")
            await grant_memory_permissions(client, "b")
            created = await client.post(
                "/api/v1/memories",
                headers=bearer("b"),
                json=memory_payload("User B private memory"),
            )
            memory_id = created.json()["id"]
            read = await client.get(f"/api/v1/memories/{memory_id}", headers=bearer("a"))
            update = await client.patch(
                f"/api/v1/memories/{memory_id}",
                headers=bearer("a"),
                json={"expected_version": 1, "content": "stolen"},
            )
            archive = await client.post(
                f"/api/v1/memories/{memory_id}/archive",
                headers=bearer("a"),
                json={"expected_version": 1},
            )
            delete = await client.delete(
                f"/api/v1/memories/{memory_id}?expected_version=1", headers=bearer("a")
            )
            listing = await client.get("/api/v1/memories", headers=bearer("a"))
            assert {
                read.status_code,
                update.status_code,
                archive.status_code,
                delete.status_code,
            } == {404}
            assert listing.json() == []

    asyncio.run(scenario())


def test_client_cannot_spoof_owner_status_provenance_confidence_or_embedding_state() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-spoof", aal="aal2")
        payload = memory_payload("Forged authority")
        payload.update(
            {
                "user_id": str(uuid4()),
                "status": "ACTIVE",
                "source_type": "SYSTEM",
                "confidence": 100,
                "embedding": [0.0, 1.0],
                "embedding_status": "READY",
            }
        )
        async with api_client({"owner": claims}) as (client, _, _):
            await grant_memory_permissions(client, "owner")
            response = await client.post("/api/v1/memories", headers=bearer("owner"), json=payload)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "INVALID_MEMORY_DATA"

    asyncio.run(scenario())


def test_source_device_must_be_owned_and_active() -> None:
    async def scenario() -> None:
        claims_a = make_claims(session_id="memory-device-a", aal="aal2")
        claims_a_fresh = make_claims(
            auth_user_id=claims_a.sub, session_id="memory-device-a-fresh", aal="aal2"
        )
        claims_b = make_claims(session_id="memory-device-b", aal="aal2")
        async with api_client({"a": claims_a, "a-fresh": claims_a_fresh, "b": claims_b}) as (
            client,
            _,
            _,
        ):
            await grant_memory_permissions(client, "a")
            foreign = await client.post(
                "/api/v1/devices/register",
                headers=bearer("b"),
                json={
                    "device_name": "Foreign browser",
                    "device_type": "WEB",
                    "platform": "WEB",
                    "device_identifier": "memory-foreign-device",
                    "capabilities": {},
                },
            )
            own = await client.post(
                "/api/v1/devices/register",
                headers=bearer("a"),
                json={
                    "device_name": "Own browser",
                    "device_type": "WEB",
                    "platform": "WEB",
                    "device_identifier": "memory-owned-device",
                    "capabilities": {},
                },
            )
            foreign_attempt = await client.post(
                "/api/v1/memories",
                headers=bearer("a"),
                json=memory_payload("Foreign origin", source_device_id=foreign.json()["id"]),
            )
            own_attempt = await client.post(
                "/api/v1/memories",
                headers=bearer("a"),
                json=memory_payload("Owned origin", source_device_id=own.json()["id"]),
            )
            await client.post(f"/api/v1/devices/{own.json()['id']}/revoke", headers=bearer("a"))
            revoked_attempt = await client.post(
                "/api/v1/memories",
                headers=bearer("a-fresh"),
                json=memory_payload("Revoked origin", source_device_id=own.json()["id"]),
            )
            assert foreign_attempt.status_code == revoked_attempt.status_code == 422
            assert own_attempt.status_code == 201

    asyncio.run(scenario())


def test_memory_capability_action_vocabulary_cannot_be_invented() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-actions", aal="aal2")
        async with api_client({"owner": claims}) as (client, _, _):
            invalid_grant = await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("memory.read", scope("memory", "delete")),
            )
            invalid_request = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("memory.read", "delete", scope("memory", "delete")),
            )
            assert invalid_grant.status_code == 422
            assert invalid_grant.json()["error"]["code"] == "ACTION_NOT_ALLOWED"
            assert invalid_request.status_code == 200
            assert invalid_request.json()["decision"] == "DENY"
            assert invalid_request.json()["reason_codes"] == ["ACTION_NOT_ALLOWED"]

    asyncio.run(scenario())


def test_high_risk_delete_uses_existing_confirmation_gate_without_bypass() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-delete-confirmation", aal="aal2")
        async with api_client({"owner": claims}) as (client, _, _):
            await grant_memory_permissions(client, "owner", delete_policy="HIGH_RISK_ONLY")
            created = await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload("Confirmed deletion"),
            )
            memory_id = created.json()["id"]
            blocked = await client.delete(
                f"/api/v1/memories/{memory_id}?expected_version=1", headers=bearer("owner")
            )
            assert blocked.status_code == 409
            assert blocked.json()["error"]["code"] == "MEMORY_CONFIRMATION_REQUIRED"
            confirmation_id = blocked.json()["confirmation_id"]
            approved = await client.post(
                f"/api/v1/confirmations/{confirmation_id}/approve", headers=bearer("owner")
            )
            deleted = await client.delete(
                f"/api/v1/memories/{memory_id}?expected_version=1&confirmation_id={confirmation_id}",
                headers=bearer("owner"),
            )
            replay = await client.delete(
                f"/api/v1/memories/{memory_id}?expected_version=1&confirmation_id={confirmation_id}",
                headers=bearer("owner"),
            )
            assert approved.status_code == 200
            assert deleted.status_code == 204
            assert replay.status_code == 403

    asyncio.run(scenario())


def test_memory_payload_bounds_and_nested_metadata_fail_closed() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-bounds", aal="aal2")
        nested: object = "leaf"
        for _ in range(8):
            nested = {"node": nested}
        async with api_client({"owner": claims}) as (client, _, _):
            await grant_memory_permissions(client, "owner")
            empty = await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload(" "),
            )
            oversized = await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload("x" * 16_001),
            )
            metadata = await client.post(
                "/api/v1/memories",
                headers=bearer("owner"),
                json=memory_payload("safe", metadata=nested),  # type: ignore[arg-type]
            )
            source_reference = memory_payload("safe")
            source_reference["source_reference"] = "x" * 256
            source = await client.post(
                "/api/v1/memories", headers=bearer("owner"), json=source_reference
            )
            assert {
                empty.status_code,
                oversized.status_code,
                metadata.status_code,
                source.status_code,
            } == {422}

    asyncio.run(scenario())


def test_public_status_restore_and_event_tampering_routes_do_not_exist() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="memory-no-force", aal="aal2")
        async with api_client({"owner": claims}) as (client, _, _):
            await grant_memory_permissions(client, "owner")
            memory_id = uuid4()
            status = await client.post(
                f"/api/v1/memories/{memory_id}/set-status",
                headers=bearer("owner"),
                json={"status": "ACTIVE"},
            )
            restore = await client.post(
                f"/api/v1/memories/{memory_id}/restore", headers=bearer("owner")
            )
            event = await client.delete(
                f"/api/v1/memories/{memory_id}/events/{uuid4()}", headers=bearer("owner")
            )
            assert status.status_code == restore.status_code == event.status_code == 404

    asyncio.run(scenario())
