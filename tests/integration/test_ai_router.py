"""AI Router persistence, fallback, usage, audit, and owner-isolation integration tests."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai_router.enums import Complexity, FailureCategory, RoutingOutcome, UsageOutcome
from backend.app.ai_router.models import AIUsageRecord, RoutingDecisionRecord
from backend.app.ai_router.observability import AIRoutingMetricEvent
from backend.app.ai_router.policy import AIRoutingPolicy
from backend.app.ai_router.provider import FakeProvider, ProviderRegistry
from backend.app.ai_router.schemas import ProviderRequest, ProviderResponse, RoutingRequest
from backend.app.ai_router.service import AIRouter, RetryPolicy
from backend.app.audit.models import AuditEvent
from backend.app.core.errors import AIProviderExecutionError, AIRoutingDeniedError
from backend.app.identity.models import User
from backend.app.permissions.enums import AuditEventType
from backend.app.security.classification import DataSensitivity
from tests.helpers import isolated_database
from tests.phase5_helpers import identity, routing_catalog


class CaptureObserver:
    def __init__(self) -> None:
        self.events: list[AIRoutingMetricEvent] = []

    def emit(self, event: AIRoutingMetricEvent) -> None:
        self.events.append(event)


def routing_request(
    *,
    complexity: Complexity = Complexity.LOW,
    sensitivity: DataSensitivity = DataSensitivity.PUBLIC,
    context_sensitivities: tuple[DataSensitivity, ...] = (),
) -> RoutingRequest:
    return RoutingRequest(
        task_type="assistant.response",
        complexity=complexity,
        sensitivity=sensitivity,
        context_sensitivities=context_sensitivities,
        estimated_input_tokens=100,
        requested_output_tokens=100,
    )


async def add_user(session: AsyncSession, user_id: UUID) -> None:
    session.add(User(id=user_id, auth_user_id=uuid4(), display_name="Router User"))
    await session.flush()


def test_route_persists_immutable_decision_without_prompt_content() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_user(session, current.user_id)
                catalog = routing_catalog()
                router = AIRouter(session, catalog, AIRoutingPolicy(catalog))
                decision = await router.route(current, routing_request())
                record = await session.get(RoutingDecisionRecord, decision.id)
                assert decision.outcome is RoutingOutcome.SELECTED
                assert record is not None
                assert record.user_id == current.user_id
                assert record.provider_key == "primary"
                assert "prompt" not in RoutingDecisionRecord.__table__.columns
                assert "content" not in RoutingDecisionRecord.__table__.columns

    asyncio.run(scenario())


def test_retryable_failure_uses_equivalent_fallback_and_records_each_attempt() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_user(session, current.user_id)
                catalog = routing_catalog()
                providers = ProviderRegistry(
                    (
                        FakeProvider("primary", (FailureCategory.TIMEOUT,)),
                        FakeProvider(
                            "equivalent",
                            (
                                ProviderResponse(
                                    output_text="safe response",
                                    input_tokens=80,
                                    output_tokens=20,
                                    actual_cost_microunits=None,
                                ),
                            ),
                        ),
                    )
                )
                router = AIRouter(
                    session,
                    catalog,
                    AIRoutingPolicy(catalog),
                    providers=providers,
                )
                result = await router.invoke(
                    current,
                    routing_request(),
                    ProviderRequest(input_text="private prompt", output_token_budget=100),
                )
                usage = list(
                    (
                        await session.scalars(
                            select(AIUsageRecord).order_by(AIUsageRecord.attempt_number)
                        )
                    ).all()
                )
                assert result.final_model.provider_key == "equivalent"
                assert [item.outcome for item in usage] == [
                    UsageOutcome.FAILURE,
                    UsageOutcome.SUCCESS,
                ]
                assert usage[0].failure_category is FailureCategory.TIMEOUT
                assert usage[1].actual_cost_microunits is None
                assert "prompt" not in AIUsageRecord.__table__.columns
                assert "response" not in AIUsageRecord.__table__.columns

    asyncio.run(scenario())


def test_permanent_failure_is_not_retried_and_attempts_are_bounded() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_user(session, current.user_id)
                catalog = routing_catalog()
                providers = ProviderRegistry(
                    (
                        FakeProvider("primary", (FailureCategory.AUTHENTICATION_ERROR,)),
                        FakeProvider(
                            "equivalent",
                            (
                                ProviderResponse(
                                    output_text="must not run", input_tokens=1, output_tokens=1
                                ),
                            ),
                        ),
                    )
                )
                router = AIRouter(
                    session,
                    catalog,
                    AIRoutingPolicy(catalog),
                    providers=providers,
                    retry_policy=RetryPolicy(max_attempts=2),
                )
                with pytest.raises(AIProviderExecutionError):
                    await router.invoke(
                        current,
                        routing_request(),
                        ProviderRequest(input_text="ephemeral", output_token_budget=100),
                    )
                count = await session.scalar(select(func.count()).select_from(AIUsageRecord))
                failure = await session.scalar(select(AIUsageRecord))
                assert count == 1
                assert failure is not None
                assert failure.failure_category is FailureCategory.AUTHENTICATION_ERROR

    asyncio.run(scenario())


def test_sensitivity_denial_is_persisted_and_security_audited_without_content() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_user(session, current.user_id)
                catalog = routing_catalog()
                router = AIRouter(session, catalog, AIRoutingPolicy(catalog))
                decision = await router.route(
                    current,
                    routing_request(
                        sensitivity=DataSensitivity.PUBLIC,
                        context_sensitivities=(DataSensitivity.CRITICAL,),
                    ),
                )
                audit = await session.scalar(select(AuditEvent))
                assert decision.outcome is RoutingOutcome.DENIED
                assert audit is not None
                assert audit.event_type is AuditEventType.AI_ROUTING_DENIED
                assert audit.metadata_payload == {"sensitivity": "CRITICAL"}

    asyncio.run(scenario())


def test_usage_query_is_owner_scoped_and_bounded() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                first = identity()
                second = identity()
                await add_user(session, first.user_id)
                await add_user(session, second.user_id)
                catalog = routing_catalog()
                response = ProviderResponse(output_text="ok", input_tokens=1, output_tokens=1)
                first_router = AIRouter(
                    session,
                    catalog,
                    AIRoutingPolicy(catalog),
                    providers=ProviderRegistry((FakeProvider("primary", (response,)),)),
                )
                second_router = AIRouter(
                    session,
                    catalog,
                    AIRoutingPolicy(catalog),
                    providers=ProviderRegistry((FakeProvider("primary", (response,)),)),
                )
                provider_request = ProviderRequest(input_text="ephemeral", output_token_budget=100)
                await first_router.invoke(first, routing_request(), provider_request)
                await second_router.invoke(second, routing_request(), provider_request)
                first_usage = await first_router.list_usage(first, limit=1_000)
                second_usage = await second_router.list_usage(second)
                assert len(first_usage) == 1
                assert len(second_usage) == 1
                assert first_usage[0].user_id == first.user_id
                assert second_usage[0].user_id == second.user_id

    asyncio.run(scenario())


def test_provider_request_cannot_expand_output_or_capabilities_after_routing() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_user(session, current.user_id)
                catalog = routing_catalog()
                router = AIRouter(session, catalog, AIRoutingPolicy(catalog))
                with pytest.raises(AIRoutingDeniedError):
                    await router.invoke(
                        current,
                        routing_request(),
                        ProviderRequest(input_text="ephemeral", output_token_budget=101),
                    )
                with pytest.raises(AIRoutingDeniedError):
                    await router.invoke(
                        current,
                        routing_request(),
                        ProviderRequest(
                            input_text="ephemeral",
                            output_token_budget=100,
                            tool_calling_required=True,
                        ),
                    )
                count = await session.scalar(
                    select(func.count()).select_from(RoutingDecisionRecord)
                )
                assert count == 0

    asyncio.run(scenario())


def test_retryable_fallback_exhaustion_is_bounded_and_observable() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_user(session, current.user_id)
                catalog = routing_catalog()
                observer = CaptureObserver()
                router = AIRouter(
                    session,
                    catalog,
                    AIRoutingPolicy(catalog),
                    providers=ProviderRegistry(
                        (
                            FakeProvider("primary", (FailureCategory.TIMEOUT,)),
                            FakeProvider("equivalent", (FailureCategory.RATE_LIMITED,)),
                        )
                    ),
                    retry_policy=RetryPolicy(max_attempts=2),
                    observer=observer,
                )
                with pytest.raises(AIProviderExecutionError):
                    await router.invoke(
                        current,
                        routing_request(),
                        ProviderRequest(input_text="ephemeral", output_token_budget=100),
                    )
                usage = list(
                    (
                        await session.scalars(
                            select(AIUsageRecord).order_by(AIUsageRecord.attempt_number)
                        )
                    ).all()
                )
                assert len(usage) == 2
                assert [item.failure_category for item in usage] == [
                    FailureCategory.TIMEOUT,
                    FailureCategory.RATE_LIMITED,
                ]
                assert [event.name for event in observer.events] == [
                    "ai.routing.selected",
                    "ai.provider.attempt",
                    "ai.provider.attempt",
                ]
                assert all("prompt" not in event.attributes for event in observer.events)

    asyncio.run(scenario())
