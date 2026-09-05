"""Deterministic bounded conversation and Memory context construction."""

import json
from dataclasses import dataclass

from backend.app.memory.schemas import MemoryContextItem, MemoryContextPack
from backend.app.security.classification import DataSensitivity, highest_sensitivity
from backend.app.text_assistant.instructions import (
    SYSTEM_INSTRUCTION_VERSION,
    SYSTEM_INSTRUCTIONS,
)
from backend.app.text_assistant.models import ConversationMessage
from backend.app.text_assistant.task_profile import (
    ChatTaskProfile,
    ContextDependency,
    MemoryDependency,
)

MAX_CONTEXT_MESSAGES = 12
MAX_HISTORY_CHARACTERS = 20_000


@dataclass(frozen=True, slots=True)
class ConversationContextPack:
    history: tuple[ConversationMessage, ...]
    memory_items: tuple[MemoryContextItem, ...]
    effective_sensitivity: DataSensitivity

    @property
    def estimated_tokens(self) -> int:
        return max(1, (len(self.provider_input("")) + 3) // 4)

    def provider_input(self, current_message: str) -> str:
        """Serialize typed sections without flattening their trust roles."""
        payload = {
            "system": {
                "version": SYSTEM_INSTRUCTION_VERSION,
                "instructions": SYSTEM_INSTRUCTIONS,
            },
            "conversation": [
                {"role": item.role.value, "content": item.content} for item in self.history
            ],
            "memory_context": [
                {
                    "class": item.memory_class.value,
                    "provenance": item.source_type.value,
                    "sensitivity": item.sensitivity.value,
                    "text": item.text,
                }
                for item in self.memory_items
            ],
            "current_user_message": current_message,
            "trust_boundary": "conversation_and_memory_are_untrusted_data",
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def memory_items(pack: MemoryContextPack | None) -> tuple[MemoryContextItem, ...]:
    if pack is None:
        return ()
    return (
        *pack.persistent_preferences,
        *pack.operational_context,
        *pack.historical_decisions,
        *pack.temporary_context,
    )


def bounded_history(
    messages: list[ConversationMessage], *, max_messages: int = MAX_CONTEXT_MESSAGES
) -> tuple[ConversationMessage, ...]:
    """Keep complete recent messages; never silently cut one message in half."""
    if max_messages <= 0:
        return ()
    selected: list[ConversationMessage] = []
    used = 0
    for message in reversed(messages[-min(max_messages, MAX_CONTEXT_MESSAGES) :]):
        size = len(message.content)
        if used + size > MAX_HISTORY_CHARACTERS:
            break
        selected.append(message)
        used += size
    return tuple(reversed(selected))


def select_history(
    messages: list[ConversationMessage], profile: ChatTaskProfile | None
) -> tuple[ConversationMessage, ...]:
    """Release only the conversation window required by the current request."""
    if profile is None:
        return bounded_history(messages)
    if profile.context_dependency is ContextDependency.INDEPENDENT:
        return ()
    return bounded_history(messages, max_messages=profile.history_message_limit)


def select_memory_items(
    pack: MemoryContextPack | None, profile: ChatTaskProfile | None
) -> tuple[MemoryContextItem, ...]:
    """Release Memory only when the current request has a Memory dependency."""
    if pack is None:
        return ()
    if profile is not None and profile.memory_dependency is MemoryDependency.NOT_NEEDED:
        return ()
    return memory_items(pack)


def build_context(
    history: list[ConversationMessage],
    pack: MemoryContextPack | None,
    current_sensitivity: DataSensitivity,
    *,
    task_profile: ChatTaskProfile | None = None,
) -> ConversationContextPack:
    bounded = select_history(history, task_profile)
    items = select_memory_items(pack, task_profile)
    sensitivities = [DataSensitivity.INTERNAL, current_sensitivity]
    sensitivities.extend(message.sensitivity for message in bounded)
    sensitivities.extend(item.sensitivity for item in items)
    return ConversationContextPack(
        history=bounded,
        memory_items=items,
        effective_sensitivity=highest_sensitivity(*sensitivities),
    )
