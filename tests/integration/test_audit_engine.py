"""Audit evidence, redaction, pagination, isolation, and failure behavior."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import func, select

from backend.app.audit.engine import AuditEngine
from backend.app.audit.models import AuditEvent
from backend.app.audit.schemas import AuditRecord
from backend.app.core.errors import AuditUnavailableError
from backend.app.permissions.dependencies import get_audit_engine
from backend.app.permissions.enums import ActorType, AuditEventType, AuditResult
from backend.app.permissions.models import AuthorizationDecisionRecord
from tests.helpers import api_client, bearer, make_claims
from tests.phase2_helpers import proposal, scope


def test_allow_deny_and_permission_events_are_visible_only_to_owner() -> None:
    async def scenario() -> None:
        claims_a = make_claims(session_id="audit-a", aal="aal2")
        claims_b = make_claims(session_id="audit-b", aal="aal2")
        async with api_client({"a": claims_a, "b": claims_b}) as (client, _, _):
            await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("a"),
                json=proposal("device.read", "read", scope("device", "read", ["a-device"])),
            )
            await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("b"),
                json=proposal("device.read", "read", scope("device", "read", ["b-device"])),
            )
            audit_a = await client.get("/api/v1/audit?limit=10&offset=0", headers=bearer("a"))
            audit_b = await client.get("/api/v1/audit?limit=10&offset=0", headers=bearer("b"))

            assert audit_a.status_code == 200
            assert audit_b.status_code == 200
            assert len(audit_a.json()) == 1
            assert len(audit_b.json()) == 1
            assert audit_a.json()[0]["event_type"] == "AUTHORIZATION_DENIED"
            assert audit_a.json()[0]["id"] != audit_b.json()[0]["id"]

    asyncio.run(scenario())


def test_audit_metadata_is_redacted_and_bounded() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="audit-redaction", aal="aal2")
        async with api_client({"owner": claims}) as (client, database, _):
            me = await client.get("/api/v1/me", headers=bearer("owner"))
            user_id = UUID(me.json()["user_id"])
            async with database.session_factory() as session:
                engine = AuditEngine(session)
                await engine.record(
                    AuditRecord(
                        user_id=user_id,
                        actor_type=ActorType.SYSTEM,
                        event_type=AuditEventType.AUTHORIZATION_DENIED,
                        result=AuditResult.DENIED,
                        metadata={
                            "access_token": "raw-secret-value",
                            "nested": {"authorization": "Bearer raw-value"},
                        },
                    )
                )
                await session.commit()

            response = await client.get("/api/v1/audit", headers=bearer("owner"))
            body = response.text
            assert "raw-secret-value" not in body
            assert "raw-value" not in body
            assert "***REDACTED***" in body

            async with database.session_factory() as session:
                with pytest.raises(ValueError, match="bounded"):
                    await AuditEngine(session).record(
                        AuditRecord(
                            user_id=user_id,
                            actor_type=ActorType.SYSTEM,
                            event_type=AuditEventType.AUTHORIZATION_DENIED,
                            result=AuditResult.DENIED,
                            metadata={"detail": "x" * 5000},
                        )
                    )

    asyncio.run(scenario())


def test_audit_is_append_oriented_and_has_no_mutation_api() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="audit-append", aal="aal2")
        async with api_client({"owner": claims}) as (client, _, _):
            response = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.read", "read", scope("device", "read", ["primary"])),
            )
            audit = await client.get("/api/v1/audit", headers=bearer("owner"))
            event_id = audit.json()[0]["id"]
            update_attempt = await client.put(
                f"/api/v1/audit/{event_id}", headers=bearer("owner"), json={}
            )
            delete_attempt = await client.delete(
                f"/api/v1/audit/{event_id}", headers=bearer("owner")
            )

            assert response.status_code == 200
            assert update_attempt.status_code == 404
            assert delete_attempt.status_code == 404

    asyncio.run(scenario())


class FailingAuditEngine(AuditEngine):
    def __init__(self) -> None:
        pass

    async def record(self, record: AuditRecord) -> AuditEvent:
        del record
        raise AuditUnavailableError


def test_required_audit_failure_rolls_back_decision_and_returns_safe_error() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="audit-failure", aal="aal2")
        async with api_client({"owner": claims}) as (client, database, application):
            application.dependency_overrides[get_audit_engine] = FailingAuditEngine
            response = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("device.read", "read", scope("device", "read", ["primary"])),
            )

            assert response.status_code == 503
            assert response.json()["error"]["code"] == "AUDIT_UNAVAILABLE"
            async with database.session_factory() as session:
                decisions = await session.scalar(
                    select(func.count()).select_from(AuthorizationDecisionRecord)
                )
                events = await session.scalar(select(func.count()).select_from(AuditEvent))
                assert decisions == 0
                assert events == 0

    asyncio.run(scenario())
