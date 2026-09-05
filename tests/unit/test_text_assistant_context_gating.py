"""Relevant context gating regressions without provider network calls."""

import json
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from backend.app.memory.enums import MemoryClass, MemorySourceType
from backend.app.memory.schemas import MemoryContextItem, MemoryContextPack
from backend.app.security.classification import DataSensitivity
from backend.app.text_assistant.context import ConversationContextPack, build_context
from backend.app.text_assistant.enums import MessageRole, MessageStatus
from backend.app.text_assistant.models import ConversationMessage
from backend.app.text_assistant.task_profile import (
    ContextDependency,
    MemoryDependency,
    profile_chat_task,
)


def _message(
    index: int, *, sensitivity: DataSensitivity = DataSensitivity.INTERNAL
) -> ConversationMessage:
    return ConversationMessage(
        id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        role=MessageRole.USER if index % 2 == 0 else MessageRole.ASSISTANT,
        status=MessageStatus.COMPLETED,
        sequence=index + 1,
        content=f"history-{index}-" + ("x" * 120),
        sensitivity=sensitivity,
        idempotency_key=f"history-key-{index}" if index % 2 == 0 else None,
        request_fingerprint="a" * 64 if index % 2 == 0 else None,
        outcome=None,
        reply_to_message_id=None,
    )


def _memory(
    index: int, sensitivity: DataSensitivity = DataSensitivity.PRIVATE
) -> MemoryContextItem:
    return MemoryContextItem(
        id=uuid4(),
        memory_class=MemoryClass.PERSISTENT_PREFERENCE,
        source_type=MemorySourceType.USER_EXPLICIT,
        source_reference=None,
        subject=f"subject-{index}",
        text=f"memory-{index}-" + ("m" * 100),
        importance=50,
        sensitivity=sensitivity,
        updated_at=datetime.now(UTC),
    )


def _pack(count: int = 4) -> MemoryContextPack:
    return MemoryContextPack(
        persistent_preferences=tuple(_memory(index) for index in range(count)),
        operational_context=(),
        historical_decisions=(),
        temporary_context=(),
    )


def _payload(context: ConversationContextPack, current: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads(context.provider_input(current)))


def test_independent_request_releases_no_history_even_when_twelve_messages_exist() -> None:
    history = [_message(index) for index in range(12)]
    profile = profile_chat_task("¿Qué puedes hacer?", requested_output_tokens=1024)
    context = build_context(
        history,
        None,
        DataSensitivity.PUBLIC,
        task_profile=profile,
    )
    assert profile.context_dependency is ContextDependency.INDEPENDENT
    assert context.history == ()
    assert _payload(context, "¿Qué puedes hacer?")["conversation"] == []


def test_independent_request_releases_no_memory_even_when_pack_is_available() -> None:
    profile = profile_chat_task("Explícame qué es una API.", requested_output_tokens=1024)
    context = build_context(
        [],
        _pack(),
        DataSensitivity.PUBLIC,
        task_profile=profile,
    )
    assert profile.memory_dependency is MemoryDependency.NOT_NEEDED
    assert context.memory_items == ()
    assert _payload(context, "Explícame qué es una API.")["memory_context"] == []


def test_independent_request_drops_both_available_history_and_memory() -> None:
    profile = profile_chat_task("¿Conoces Google?", requested_output_tokens=1024)
    context = build_context(
        [_message(index) for index in range(12)],
        _pack(),
        DataSensitivity.PUBLIC,
        task_profile=profile,
    )
    assert context.history == ()
    assert context.memory_items == ()


def test_immediate_followup_keeps_only_recent_context_window() -> None:
    history = [_message(index) for index in range(12)]
    for content in ("¿Y cuánto cuesta?", "Explícame mejor lo que acabas de decir."):
        profile = profile_chat_task(content, requested_output_tokens=1024)
        context = build_context(
            history,
            None,
            DataSensitivity.PUBLIC,
            task_profile=profile,
        )
        assert profile.context_dependency is ContextDependency.PRIOR_CONTEXT
        assert profile.history_message_limit == 4
        assert len(context.history) == 4
        assert [item.sequence for item in context.history] == [9, 10, 11, 12]


def test_explicit_older_reference_preserves_extended_bounded_window() -> None:
    history = [_message(index) for index in range(12)]
    profile = profile_chat_task(
        "Compara las alternativas que discutimos anteriormente.",
        requested_output_tokens=1024,
    )
    context = build_context(
        history,
        None,
        DataSensitivity.PUBLIC,
        task_profile=profile,
    )
    assert profile.context_dependency is ContextDependency.PRIOR_CONTEXT
    assert profile.history_message_limit == 12
    assert len(context.history) == 12


def test_personal_fact_and_explicit_recall_are_memory_dependent() -> None:
    for content in (
        "¿Cuál es mi color favorito?",
        "Según lo que recuerdas de mí, ¿qué prefiero?",
        "¿Qué habíamos decidido sobre mi proyecto?",
    ):
        profile = profile_chat_task(content, requested_output_tokens=1024)
        assert profile.memory_dependency is MemoryDependency.NEEDED
        context = build_context(
            [],
            _pack(),
            DataSensitivity.PUBLIC,
            task_profile=profile,
        )
        assert len(context.memory_items) == 4


def test_selected_sensitive_context_never_downgrades_effective_sensitivity() -> None:
    profile = profile_chat_task("¿Cuál es mi color favorito?", requested_output_tokens=1024)
    pack = MemoryContextPack(
        persistent_preferences=(_memory(1, DataSensitivity.CRITICAL),),
        operational_context=(),
        historical_decisions=(),
        temporary_context=(),
    )
    context = build_context(
        [],
        pack,
        DataSensitivity.PRIVATE,
        task_profile=profile,
    )
    assert context.effective_sensitivity is DataSensitivity.CRITICAL


def test_current_sensitive_request_remains_sensitive_without_optional_context() -> None:
    profile = profile_chat_task("¿Qué puedes hacer?", requested_output_tokens=1024)
    context = build_context(
        [_message(index, sensitivity=DataSensitivity.CRITICAL) for index in range(12)],
        _pack(),
        DataSensitivity.SENSITIVE,
        task_profile=profile,
    )
    assert context.history == ()
    assert context.memory_items == ()
    assert context.effective_sensitivity is DataSensitivity.SENSITIVE


def test_offline_context_reduction_fixture_is_material() -> None:
    history = [_message(index) for index in range(12)]
    pack = _pack(12)
    old_context = build_context(history, pack, DataSensitivity.PUBLIC)
    profile = profile_chat_task("¿Qué puedes hacer?", requested_output_tokens=1024)
    new_context = build_context(
        history,
        pack,
        DataSensitivity.PUBLIC,
        task_profile=profile,
    )
    old_chars = len(old_context.provider_input("¿Qué puedes hacer?"))
    new_chars = len(new_context.provider_input("¿Qué puedes hacer?"))
    old_tokens = (old_chars + 3) // 4
    new_tokens = (new_chars + 3) // 4

    assert len(old_context.history) == 12
    assert len(old_context.memory_items) == 12
    assert len(new_context.history) == 0
    assert len(new_context.memory_items) == 0
    assert new_chars < old_chars
    assert new_tokens < old_tokens
    assert 1 - (new_chars / old_chars) > 0.70
