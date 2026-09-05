"""Regression coverage for task complexity, history independence, and output budgets."""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai_router.enums import ModelClass
from backend.app.ai_router.models import RoutingDecisionRecord
from backend.app.text_assistant.schemas import AssistantRequest, ConversationCreateRequest
from tests.helpers import isolated_database
from tests.phase5_helpers import identity
from tests.phase6_helpers import add_identity_user, provider_response
from tests.phase7_helpers import build_text_assistant


def _message(
    content: str,
    *,
    key: str,
    version: int,
    requested_output_tokens: int = 1024,
) -> AssistantRequest:
    return AssistantRequest(
        content=content,
        idempotency_key=key,
        expected_version=version,
        use_memory_context=False,
        requested_output_tokens=requested_output_tokens,
    )


async def _latest_decision(session: AsyncSession) -> RoutingDecisionRecord:
    decision = await session.scalar(
        select(RoutingDecisionRecord).order_by(
            RoutingDecisionRecord.created_at.desc(),
            RoutingDecisionRecord.id.desc(),
        )
    )
    assert decision is not None
    return decision


@pytest.mark.parametrize(
    "prior_turns", [0, 1, 6], ids=["no-history", "two-messages", "twelve-messages"]
)
def test_simple_question_stays_fast_regardless_of_history_size(prior_turns: int) -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                service, _, _ = build_text_assistant(
                    session,
                    tuple(provider_response("ok") for _ in range(prior_turns + 1)),
                )
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                for index in range(prior_turns):
                    await service.submit(
                        current,
                        conversation.id,
                        _message(
                            "Mensaje previo irrelevante.",
                            key=f"prior-key-{index}",
                            version=index + 1,
                        ),
                    )
                await service.submit(
                    current,
                    conversation.id,
                    _message(
                        "¿Qué puedes hacer?",
                        key="current-simple",
                        version=prior_turns + 1,
                    ),
                )
                decision = await _latest_decision(session)
                assert decision.model_class is ModelClass.FAST
                assert decision.requested_output_tokens == 384

    asyncio.run(scenario())


def test_context_dependent_simple_task_keeps_history_without_complexity_escalation() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                service, _, _ = build_text_assistant(
                    session,
                    tuple(provider_response("ok") for _ in range(3)),
                )

                without_history = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                await service.submit(
                    current,
                    without_history.id,
                    _message(
                        "¿Qué me dijiste antes sobre eso?",
                        key="without-history",
                        version=1,
                    ),
                )
                baseline = await _latest_decision(session)

                with_history = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                await service.submit(
                    current,
                    with_history.id,
                    _message(
                        "La referencia necesaria es API REST.",
                        key="context-key",
                        version=1,
                    ),
                )
                await service.submit(
                    current,
                    with_history.id,
                    _message(
                        "¿Qué me dijiste antes sobre eso?",
                        key="with-history",
                        version=2,
                    ),
                )
                contextual = await _latest_decision(session)

                assert baseline.model_class is ModelClass.FAST
                assert contextual.model_class is ModelClass.FAST
                assert contextual.estimated_input_tokens > baseline.estimated_input_tokens

    asyncio.run(scenario())


def test_real_comparison_routes_standard_with_larger_budget() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                service, _, _ = build_text_assistant(session, (provider_response("ok"),))
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                await service.submit(
                    current,
                    conversation.id,
                    _message(
                        "Compara estas alternativas y evalúa sus riesgos.",
                        key="medium-task",
                        version=1,
                        requested_output_tokens=2048,
                    ),
                )
                decision = await _latest_decision(session)
                assert decision.model_class is ModelClass.STANDARD
                assert decision.requested_output_tokens == 1024

    asyncio.run(scenario())


def test_explicit_deep_analysis_routes_advanced_without_low_budget_cap() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                service, _, _ = build_text_assistant(session, (provider_response("ok"),))
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                await service.submit(
                    current,
                    conversation.id,
                    _message(
                        "Haz un análisis profundo y compara cada alternativa rigurosamente.",
                        key="high-task",
                        version=1,
                        requested_output_tokens=2048,
                    ),
                )
                decision = await _latest_decision(session)
                assert decision.model_class is ModelClass.ADVANCED
                assert decision.requested_output_tokens == 2048

    asyncio.run(scenario())
