"""Authority, privacy, prompt-injection, and future-executor security boundaries."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from backend.app.ai_router.models import AIUsageRecord, RoutingDecisionRecord
from backend.app.audit.engine import AuditEngine
from backend.app.audit.models import AuditEvent
from backend.app.core.config import Environment, Settings
from backend.app.core.errors import OrchestrationNotFoundError, TaskDeviceInvalidError
from backend.app.identity.models import Device, DeviceType, utc_now
from backend.app.main import create_app
from backend.app.memory.enums import MemoryClass, MemoryStatus
from backend.app.memory.schemas import MemoryCreateRequest
from backend.app.orchestrator.enums import IntentCategory, OrchestrationState, SafeMode
from backend.app.orchestrator.models import OrchestrationStep, OrchestrationWorkflow, ValidatedPlan
from backend.app.orchestrator.schemas import CandidatePlan, IntentMetadata, OrchestrationRequest
from backend.app.permissions.enums import ConfirmationPolicy
from backend.app.permissions.models import ConfirmationRequest
from backend.app.permissions.service import PermissionAdministrationService
from backend.app.security.classification import DataSensitivity
from tests.helpers import isolated_database
from tests.phase5_helpers import identity
from tests.phase6_helpers import (
    add_identity_user,
    build_orchestrator,
    candidate_plan,
    grant,
    provider_response,
)


def command(
    category: IntentCategory = IntentCategory.ACTION,
    *,
    text: str = "untrusted input",
    key: str = "security-orchestration-key",
    use_memory: bool = False,
) -> OrchestrationRequest:
    return OrchestrationRequest(
        intent=IntentMetadata(category=category, label="security.test"),
        input_text=text,
        idempotency_key=key,
        use_memory_context=use_memory,
        requested_output_tokens=512,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("user_id", "00000000-0000-0000-0000-000000000001"),
        ("authenticated", True),
        ("risk_level", 0),
        ("permission_granted", True),
        ("confirmation_satisfied", True),
        ("provider", "attacker-provider"),
        ("model", "weak-model"),
        ("sensitivity", "PUBLIC"),
        ("safe_mode", "NORMAL"),
        ("force_state", "READY_FOR_EXECUTION"),
    ],
)
def test_public_request_rejects_client_authority_fields(field: str, value: object) -> None:
    payload = {
        "intent": {"category": "ACTION", "label": "security.test"},
        "input_text": "request",
        "idempotency_key": "security-authority-key",
        field: value,
    }
    with pytest.raises(ValidationError):
        OrchestrationRequest.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("risk_level", 0),
        ("permission_granted", True),
        ("confirmation_satisfied", True),
        ("provider", "untrusted"),
        ("model", "untrusted"),
        ("execute", True),
    ],
)
def test_model_plan_rejects_authority_claims(field: str, value: object) -> None:
    payload = {
        "summary": "proposal",
        "actions": [],
        field: value,
    }
    with pytest.raises(ValidationError):
        CandidatePlan.model_validate(payload)


def test_candidate_plan_fingerprint_binds_material_arguments() -> None:
    first = CandidatePlan.model_validate_json(
        candidate_plan(
            "notification.send",
            "send",
            resource_type="notification",
            arguments={"target": "one"},
        )
    )
    changed = CandidatePlan.model_validate_json(
        candidate_plan(
            "notification.send",
            "send",
            resource_type="notification",
            arguments={"target": "two"},
        )
    )
    assert first.fingerprint != changed.fingerprint


def test_no_public_executor_or_envelope_mutation_route_exists() -> None:
    application = create_app(Settings(environment=Environment.LOCAL))
    paths = {getattr(route, "path", "") for route in application.routes}
    forbidden = {
        "/api/v1/execute-anything",
        "/api/v1/run-tool",
        "/api/v1/force-plan",
        "/api/v1/force-model",
        "/api/v1/force-state",
        "/api/v1/skip-confirmation",
        "/api/v1/authorized-action-envelopes",
    }
    assert paths.isdisjoint(forbidden)


def test_critical_memory_fails_routing_before_provider_invocation() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                await grant(session, current, "memory.read", "read", "memory")
                await grant(session, current, "memory.write", "create", "memory")
                service, providers = build_orchestrator(
                    session, (provider_response("must not be invoked"),)
                )
                stored = await service.memory.create_explicit(
                    current,
                    MemoryCreateRequest(
                        memory_class=MemoryClass.PERSISTENT_PREFERENCE,
                        content="critical private fact",
                        subject="critical",
                        sensitivity=DataSensitivity.CRITICAL,
                    ),
                )
                assert stored.value is not None
                result = await service.create(
                    current,
                    command(IntentCategory.INFORMATIONAL, use_memory=True),
                )
                assert result.workflow.state is OrchestrationState.DENIED
                assert result.workflow.failure_reason == "SENSITIVITY_ROUTING_DENIED"
                assert all(provider.call_count == 0 for provider in providers.values())

    asyncio.run(scenario())


@pytest.mark.parametrize("terminal_operation", ["expired", "deleted"])
def test_expired_or_deleted_memory_is_excluded_from_orchestrator_context(
    terminal_operation: str,
) -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                await grant(session, current, "memory.read", "read", "memory")
                await grant(session, current, "memory.write", "create", "memory")
                if terminal_operation == "deleted":
                    await grant(session, current, "memory.delete", "delete", "memory")
                service, _ = build_orchestrator(session, (provider_response("safe"),))
                create = MemoryCreateRequest(
                    memory_class=(
                        MemoryClass.TEMPORARY_CONTEXT
                        if terminal_operation == "expired"
                        else MemoryClass.PERSISTENT_PREFERENCE
                    ),
                    content="must not enter provider context",
                    subject="excluded",
                    expires_at=(
                        datetime.now(UTC) + timedelta(minutes=5)
                        if terminal_operation == "expired"
                        else None
                    ),
                )
                stored = await service.memory.create_explicit(current, create)
                assert stored.value is not None
                if terminal_operation == "expired":
                    stored.value.created_at = datetime.now(UTC) - timedelta(minutes=10)
                    stored.value.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                    await session.flush()
                else:
                    deleted = await service.memory.delete_owned(
                        current,
                        stored.value.id,
                        expected_version=stored.value.version,
                        confirmation_id=None,
                    )
                    assert deleted.value is not None
                    assert deleted.value.status is MemoryStatus.DELETED
                result = await service.create(
                    current,
                    command(
                        IntentCategory.INFORMATIONAL,
                        key=f"excluded-{terminal_operation}-memory",
                        use_memory=True,
                    ),
                )
                step = await session.scalar(
                    select(OrchestrationStep).where(
                        OrchestrationStep.workflow_id == result.workflow.id,
                        OrchestrationStep.reason_code == "CONTEXT_READY",
                    )
                )
                assert step is not None
                assert step.metadata_payload["memory_item_count"] == 0

    asyncio.run(scenario())


def test_raw_prompt_is_absent_from_persistence_and_audit() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                marker = "PRIVATE-PROMPT-MARKER-DO-NOT-PERSIST"
                service, _ = build_orchestrator(session, (provider_response("answer"),))
                result = await service.create(
                    current,
                    command(IntentCategory.INFORMATIONAL, text=marker),
                )
                workflow = await session.get(OrchestrationWorkflow, result.workflow.id)
                assert workflow is not None
                assert marker not in str(workflow.intent_metadata)
                records: list[object] = []
                records.extend(list(await session.scalars(select(OrchestrationStep))))
                records.extend(list(await session.scalars(select(AuditEvent))))
                records.extend(list(await session.scalars(select(RoutingDecisionRecord))))
                records.extend(list(await session.scalars(select(AIUsageRecord))))
                assert all(marker not in repr(record.__dict__) for record in records)

    asyncio.run(scenario())


def test_feature_flag_cannot_override_safe_mode() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                output = candidate_plan("device.read", "read", resource_type="device")
                service, providers = build_orchestrator(
                    session,
                    (provider_response(output),),
                    safe_mode=SafeMode.SAFE_MODE,
                    ai_enabled=True,
                    actions_enabled=True,
                )
                result = await service.create(current, command())
                assert result.workflow.state is OrchestrationState.DENIED
                assert all(provider.call_count == 0 for provider in providers.values())

    asyncio.run(scenario())


def test_model_cannot_mark_confirmation_satisfied() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                await grant(
                    session,
                    current,
                    "notification.send",
                    "send",
                    "notification",
                    confirmation_policy=ConfirmationPolicy.EVERY_TIME,
                )
                payload = candidate_plan("notification.send", "send", resource_type="notification")
                parsed = __import__("json").loads(payload)
                parsed["confirmation_satisfied"] = True
                service, _ = build_orchestrator(
                    session, (provider_response(__import__("json").dumps(parsed)),)
                )
                result = await service.create(current, command())
                assert result.workflow.state is OrchestrationState.FAILED
                assert result.workflow.failure_reason == "INVALID_MODEL_PROPOSAL"

    asyncio.run(scenario())


def test_confirmation_cannot_authorize_materially_changed_plan() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                await grant(
                    session,
                    current,
                    "notification.send",
                    "send",
                    "notification",
                    confirmation_policy=ConfirmationPolicy.EVERY_TIME,
                )
                original = candidate_plan(
                    "notification.send",
                    "send",
                    resource_type="notification",
                    arguments={"target": "original"},
                )
                service, _ = build_orchestrator(session, (provider_response(original),))
                waiting = await service.create(current, command())
                confirmation_id = waiting.workflow.confirmation_request_id
                assert confirmation_id is not None
                admin = PermissionAdministrationService(session, AuditEngine(session))
                await admin.approve_confirmation(current, confirmation_id)

                stored = await session.scalar(
                    select(ValidatedPlan).where(ValidatedPlan.workflow_id == waiting.workflow.id)
                )
                assert stored is not None
                stored.plan_payload = CandidatePlan.model_validate_json(
                    candidate_plan(
                        "notification.send",
                        "send",
                        resource_type="notification",
                        arguments={"target": "changed-after-confirmation"},
                    )
                ).model_dump(mode="json")
                await session.flush()

                resumed = await service.resume(
                    current, waiting.workflow.id, waiting.workflow.version
                )
                assert resumed.workflow.state is OrchestrationState.DENIED
                assert resumed.workflow.failure_reason == "PLAN_INTEGRITY_FAILURE"
                assert not resumed.envelope_created
                assert await service.get_envelope_internal(current, waiting.workflow.id) is None

    asyncio.run(scenario())


def test_expired_confirmation_cannot_make_workflow_ready() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                await grant(
                    session,
                    current,
                    "notification.send",
                    "send",
                    "notification",
                    confirmation_policy=ConfirmationPolicy.EVERY_TIME,
                )
                output = candidate_plan("notification.send", "send", resource_type="notification")
                service, _ = build_orchestrator(session, (provider_response(output),))
                waiting = await service.create(
                    current, command(key="expired-confirmation-workflow")
                )
                confirmation_id = waiting.workflow.confirmation_request_id
                assert confirmation_id is not None
                confirmation = await session.get(ConfirmationRequest, confirmation_id)
                assert confirmation is not None
                confirmation.requested_at = utc_now() - timedelta(minutes=2)
                confirmation.expires_at = utc_now() - timedelta(minutes=1)
                await session.flush()

                resumed = await service.resume(
                    current, waiting.workflow.id, waiting.workflow.version
                )
                assert resumed.workflow.state is OrchestrationState.DENIED
                assert not resumed.envelope_created
                assert await service.get_envelope_internal(current, waiting.workflow.id) is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "operation",
    [
        "buy",
        "sell",
        "transfer",
        "withdraw",
        "deposit",
        "place_order",
        "change_leverage",
        "increase_risk",
        "execute",
    ],
)
def test_every_financial_execution_operation_is_denied_before_handoff(
    operation: str,
) -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                await grant(session, current, "finance.execute", operation, "finance")
                output = candidate_plan("finance.execute", operation, resource_type="finance")
                service, _ = build_orchestrator(session, (provider_response(output),))
                result = await service.create(
                    current,
                    command(
                        IntentCategory.DESTRUCTIVE,
                        key=f"financial-hard-deny-{operation}",
                    ),
                )
                assert result.workflow.state is OrchestrationState.DENIED
                assert result.workflow.failure_reason == "FINANCIAL_EXECUTION_PROHIBITED"
                assert result.workflow.task_id is None
                assert not result.envelope_created
                assert await service.get_envelope_internal(current, result.workflow.id) is None

    asyncio.run(scenario())


def test_foreign_device_identity_cannot_create_action_task() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                owner = identity()
                other = identity()
                await add_identity_user(session, owner)
                await add_identity_user(session, other)
                foreign = Device(
                    user_id=other.user_id,
                    device_name="Foreign",
                    device_type=DeviceType.WEB,
                    platform="web",
                    device_identifier="foreign-install-001",
                    capabilities={},
                )
                session.add(foreign)
                await session.flush()
                forged = owner.model_copy(update={"device_id": foreign.id})
                await grant(session, owner, "device.read", "read", "device")
                output = candidate_plan("device.read", "read", resource_type="device")
                service, _ = build_orchestrator(session, (provider_response(output),))
                with pytest.raises(TaskDeviceInvalidError):
                    await service.create(forged, command())

    asyncio.run(scenario())


def test_cross_user_cancellation_is_not_observable() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                owner = identity()
                other = identity()
                await add_identity_user(session, owner)
                await add_identity_user(session, other)
                service, _ = build_orchestrator(session, (provider_response("answer"),))
                created = await service.create(owner, command(IntentCategory.INFORMATIONAL))
                with pytest.raises(OrchestrationNotFoundError):
                    await service.cancel(other, created.workflow.id, created.workflow.version)

    asyncio.run(scenario())


def test_validated_plan_has_no_public_mutation_endpoint() -> None:
    application = create_app(Settings(environment=Environment.LOCAL))
    paths = {getattr(route, "path", "") for route in application.routes}
    assert "/api/v1/orchestrations/{workflow_id}/plan" not in paths
    assert "plan_payload" in ValidatedPlan.__table__.columns
