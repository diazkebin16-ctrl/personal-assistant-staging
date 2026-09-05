"""Integration coverage for server-owned history and Memory relevance gating."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from backend.app.memory.enums import MemoryClass, MemorySourceType
from backend.app.memory.schemas import MemoryContextItem, MemoryContextPack
from backend.app.security.classification import DataSensitivity
from backend.app.text_assistant.observability import TextAssistantMetricEvent
from backend.app.text_assistant.schemas import AssistantRequest, ConversationCreateRequest
from tests.helpers import isolated_database
from tests.phase5_helpers import identity
from tests.phase6_helpers import add_identity_user, provider_response
from tests.phase7_helpers import build_text_assistant


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[TextAssistantMetricEvent] = []

    def emit(self, event: TextAssistantMetricEvent) -> None:
        self.events.append(event)

    def context_event(self) -> TextAssistantMetricEvent:
        matches = [
            event for event in self.events if event.name == "text_assistant.context.selected"
        ]
        assert matches
        return matches[-1]


def _request(
    content: str,
    *,
    key: str,
    version: int,
    use_memory_context: bool = True,
) -> AssistantRequest:
    return AssistantRequest(
        content=content,
        idempotency_key=key,
        expected_version=version,
        use_memory_context=use_memory_context,
        requested_output_tokens=1024,
    )


def _memory_pack() -> MemoryContextPack:
    item = MemoryContextItem(
        id=uuid4(),
        memory_class=MemoryClass.PERSISTENT_PREFERENCE,
        source_type=MemorySourceType.USER_EXPLICIT,
        source_reference=None,
        subject="favorite-color",
        text="El color favorito del usuario es azul.",
        importance=80,
        sensitivity=DataSensitivity.PRIVATE,
        updated_at=datetime.now(UTC),
    )
    return MemoryContextPack(
        persistent_preferences=(item,),
        operational_context=(),
        historical_decisions=(),
        temporary_context=(),
    )


def test_independent_chat_with_history_and_memory_permission_queries_no_memory() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                service, _, _ = build_text_assistant(
                    session,
                    tuple(provider_response("ok") for _ in range(7)),
                )
                observer = RecordingObserver()
                service.observer = observer

                async def fail_if_memory_queried(*args, **kwargs):
                    del args, kwargs
                    raise AssertionError("independent chat must not query Memory")

                service.memory.build_context_pack = fail_if_memory_queried  # type: ignore[method-assign]
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                for index in range(6):
                    await service.submit(
                        current,
                        conversation.id,
                        _request(
                            "Mensaje previo irrelevante.",
                            key=f"prior-context-{index}",
                            version=index + 1,
                            use_memory_context=False,
                        ),
                    )
                await service.submit(
                    current,
                    conversation.id,
                    _request(
                        "¿Qué puedes hacer?",
                        key="independent-current",
                        version=7,
                        use_memory_context=True,
                    ),
                )
                attributes = observer.context_event().attributes
                assert attributes["history_messages_available"] == 12
                assert attributes["history_messages_included"] == 0
                assert attributes["history_chars_included"] == 0
                assert attributes["memory_context_authorized"] is True
                assert attributes["memory_context_queried"] is False
                assert attributes["memory_items_included"] == 0

    asyncio.run(scenario())


def test_immediate_followup_keeps_small_recent_window() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                service, _, _ = build_text_assistant(
                    session,
                    tuple(provider_response("ok") for _ in range(4)),
                )
                observer = RecordingObserver()
                service.observer = observer
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                for index in range(3):
                    await service.submit(
                        current,
                        conversation.id,
                        _request(
                            "Una respuesta previa con contexto.",
                            key=f"followup-prior-{index}",
                            version=index + 1,
                            use_memory_context=False,
                        ),
                    )
                await service.submit(
                    current,
                    conversation.id,
                    _request(
                        "¿Y cuánto cuesta?",
                        key="followup-current",
                        version=4,
                        use_memory_context=False,
                    ),
                )
                attributes = observer.context_event().attributes
                assert attributes["history_messages_available"] == 6
                assert attributes["history_messages_included"] == 4
                assert attributes["context_dependency"] == "PRIOR_CONTEXT"

    asyncio.run(scenario())


def test_memory_dependent_chat_queries_memory_only_when_authorized() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                service, _, _ = build_text_assistant(
                    session,
                    (provider_response("sin memoria"), provider_response("con memoria")),
                )
                observer = RecordingObserver()
                service.observer = observer
                calls = 0

                async def memory_context(*args, **kwargs):
                    nonlocal calls
                    del args, kwargs
                    calls += 1
                    return SimpleNamespace(value=_memory_pack())

                service.memory.build_context_pack = memory_context  # type: ignore[method-assign]

                unauthorized = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                await service.submit(
                    current,
                    unauthorized.id,
                    _request(
                        "¿Cuál es mi color favorito?",
                        key="memory-disabled",
                        version=1,
                        use_memory_context=False,
                    ),
                )
                disabled = observer.context_event().attributes
                assert calls == 0
                assert disabled["memory_dependency"] == "NEEDED"
                assert disabled["memory_context_authorized"] is False
                assert disabled["memory_context_queried"] is False
                assert disabled["memory_items_included"] == 0

                authorized = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                await service.submit(
                    current,
                    authorized.id,
                    _request(
                        "Según lo que recuerdas de mí, ¿qué prefiero?",
                        key="memory-enabled",
                        version=1,
                        use_memory_context=True,
                    ),
                )
                enabled = observer.context_event().attributes
                assert calls == 1
                assert enabled["memory_dependency"] == "NEEDED"
                assert enabled["memory_context_queried"] is True
                assert enabled["memory_items_included"] == 1

    asyncio.run(scenario())


def test_context_metrics_contain_structure_not_history_or_memory_content() -> None:
    event = TextAssistantMetricEvent(
        name="text_assistant.context.selected",
        attributes={
            "history_messages_available": 12,
            "history_messages_included": 0,
            "history_chars_included": 0,
            "memory_context_authorized": True,
            "memory_context_queried": False,
            "memory_items_included": 0,
            "context_dependency": "INDEPENDENT",
            "memory_dependency": "NOT_NEEDED",
            "estimated_input_tokens": 100,
        },
    )
    serialized = repr(event.attributes)
    assert "history-" not in serialized
    assert "favorite-color" not in serialized
    assert "memory-" not in serialized
