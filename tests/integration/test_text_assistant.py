"""Phase 7 conversation, Memory, routing, orchestration, and idempotency flows."""

import asyncio

import pytest
from sqlalchemy import select

from backend.app.core.errors import (
    ConversationConcurrentModificationError,
    ConversationNotFoundError,
    MessageIdempotencyConflictError,
)
from backend.app.memory.enums import MemoryClass
from backend.app.memory.schemas import MemoryCreateRequest
from backend.app.security.classification import DataSensitivity
from backend.app.text_assistant.enums import AssistantOutcome
from backend.app.text_assistant.models import ConversationMessage
from backend.app.text_assistant.schemas import AssistantRequest, ConversationCreateRequest
from tests.helpers import isolated_database
from tests.phase5_helpers import identity
from tests.phase6_helpers import (
    add_identity_user,
    candidate_plan,
    grant,
    provider_response,
)
from tests.phase7_helpers import build_text_assistant


def message(
    content: str,
    *,
    key: str = "text-message-key",
    version: int = 1,
    use_memory: bool = False,
) -> AssistantRequest:
    return AssistantRequest(
        content=content,
        idempotency_key=key,
        expected_version=version,
        use_memory_context=use_memory,
        requested_output_tokens=512,
    )


def test_end_to_end_text_conversation_persists_both_messages() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                service, providers, _ = build_text_assistant(
                    session, (provider_response("Respuesta natural y veraz."),)
                )
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest(title="Primera conversación")
                )
                result = await service.submit(
                    current, conversation.id, message("Hola, ayúdame a pensar.")
                )
                assert result.assistant_message.content == "Respuesta natural y veraz."
                assert result.assistant_message.outcome is AssistantOutcome.ANSWERED
                assert result.assistant_message.sequence == 2
                records = list(await session.scalars(select(ConversationMessage)))
                assert [record.sequence for record in records] == [1, 2]
                assert providers["primary"].call_count == 1

    asyncio.run(scenario())


def test_explicit_memory_command_uses_memory_service_and_reports_truth() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                await grant(session, current, "memory.write", "create", "memory")
                service, providers, _ = build_text_assistant(session, ())
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                result = await service.submit(
                    current,
                    conversation.id,
                    message("recuerda que prefiero respuestas directas"),
                )
                assert result.assistant_message.outcome is AssistantOutcome.MEMORY_SAVED
                assert result.assistant_message.memory_id is not None
                assert "recordar" in result.assistant_message.content.casefold()
                assert all(provider.call_count == 0 for provider in providers.values())

    asyncio.run(scenario())


def test_actionable_request_uses_orchestrator_and_never_claims_execution() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                plan = candidate_plan("notification.send", "send", resource_type="notification")
                service, _, orchestration_providers = build_text_assistant(
                    session, (), orchestration_outcomes=(provider_response(plan),)
                )
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                result = await service.submit(
                    current, conversation.id, message("send a notification", use_memory=False)
                )
                assert (
                    result.assistant_message.outcome is AssistantOutcome.ACTION_WAITING_PERMISSION
                )
                assert result.assistant_message.orchestration_id is not None
                assert "realiz" not in result.assistant_message.content.casefold()
                assert orchestration_providers["primary"].call_count == 1

    asyncio.run(scenario())


def test_idempotent_retry_returns_same_pair_without_second_provider_call() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                service, providers, _ = build_text_assistant(
                    session, (provider_response("only once"),)
                )
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                command = message("hello")
                first = await service.submit(current, conversation.id, command)
                second = await service.submit(current, conversation.id, command)
                assert first.user_message.id == second.user_message.id
                assert first.assistant_message.id == second.assistant_message.id
                assert providers["primary"].call_count == 1

    asyncio.run(scenario())


def test_same_idempotency_key_with_changed_request_conflicts() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                service, _, _ = build_text_assistant(session, (provider_response("first"),))
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                await service.submit(current, conversation.id, message("one"))
                with pytest.raises(MessageIdempotencyConflictError):
                    await service.submit(
                        current,
                        conversation.id,
                        message("two", version=2),
                    )

    asyncio.run(scenario())


def test_stale_conversation_version_is_rejected_without_mutation() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                service, _, _ = build_text_assistant(session, (provider_response("first"),))
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                await service.submit(current, conversation.id, message("one"))
                with pytest.raises(ConversationConcurrentModificationError):
                    await service.submit(
                        current,
                        conversation.id,
                        message("two", key="second-key", version=1),
                    )

    asyncio.run(scenario())


def test_cross_user_conversation_and_message_access_is_not_found() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                owner = identity()
                other = identity()
                await add_identity_user(session, owner)
                await add_identity_user(session, other)
                service, _, _ = build_text_assistant(session, ())
                conversation = await service.create_conversation(owner, ConversationCreateRequest())
                with pytest.raises(ConversationNotFoundError):
                    await service.get_owned(other, conversation.id)
                with pytest.raises(ConversationNotFoundError):
                    await service.list_messages(other, conversation.id, limit=100, offset=0)

    asyncio.run(scenario())


def test_critical_memory_fails_closed_before_external_provider_invocation() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                await grant(session, current, "memory.read", "read", "memory")
                await grant(session, current, "memory.write", "create", "memory")
                service, providers, _ = build_text_assistant(
                    session, (provider_response("must not be called"),)
                )
                stored = await service.memory.create_explicit(
                    current,
                    MemoryCreateRequest(
                        memory_class=MemoryClass.PERSISTENT_PREFERENCE,
                        content="critical context marker",
                        sensitivity=DataSensitivity.CRITICAL,
                    ),
                )
                assert stored.value is not None
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                result = await service.submit(
                    current, conversation.id, message("hello", use_memory=True)
                )
                assert result.assistant_message.status.value == "FAILED"
                assert result.assistant_message.sensitivity is DataSensitivity.CRITICAL
                assert all(provider.call_count == 0 for provider in providers.values())

    asyncio.run(scenario())


def test_authorized_action_is_truthfully_ready_but_not_executed() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                await grant(session, current, "notification.send", "send", "notification")
                plan = candidate_plan("notification.send", "send", resource_type="notification")
                service, _, _ = build_text_assistant(
                    session, (), orchestration_outcomes=(provider_response(plan),)
                )
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                result = await service.submit(
                    current, conversation.id, message("send a notification")
                )
                assert (
                    result.assistant_message.outcome
                    is AssistantOutcome.ACTION_READY_FOR_FUTURE_EXECUTION
                )
                content = result.assistant_message.content.casefold()
                assert "no se realizó" in content
                assert "ejecutor" in content

    asyncio.run(scenario())


def test_sensitive_memory_routes_only_to_sensitivity_approved_provider() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                await grant(session, current, "memory.read", "read", "memory")
                await grant(session, current, "memory.write", "create", "memory")
                service, providers, _ = build_text_assistant(
                    session, (provider_response("safely routed"),)
                )
                stored = await service.memory.create_explicit(
                    current,
                    MemoryCreateRequest(
                        memory_class=MemoryClass.PERSISTENT_PREFERENCE,
                        content="sensitive preference",
                        sensitivity=DataSensitivity.SENSITIVE,
                    ),
                )
                assert stored.value is not None
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                result = await service.submit(
                    current, conversation.id, message("hello", use_memory=True)
                )
                assert result.assistant_message.outcome is AssistantOutcome.ANSWERED
                assert providers["sensitive-approved"].call_count == 1
                assert providers["primary"].call_count == 0

    asyncio.run(scenario())
