"""Semantic chat task profiling independent of conversation size."""

import re
from dataclasses import dataclass
from enum import StrEnum

from backend.app.ai_router.enums import Complexity


class ContextDependency(StrEnum):
    """Whether the current request depends on prior conversation context."""

    INDEPENDENT = "INDEPENDENT"
    PRIOR_CONTEXT = "PRIOR_CONTEXT"


class MemoryDependency(StrEnum):
    """Whether user Memory can materially help answer the current request."""

    NOT_NEEDED = "NOT_NEEDED"
    NEEDED = "NEEDED"


@dataclass(frozen=True, slots=True)
class ChatTaskProfile:
    """Server-owned task semantics used for routing and context release."""

    complexity: Complexity
    context_dependency: ContextDependency
    memory_dependency: MemoryDependency
    history_message_limit: int
    output_token_budget: int


RECENT_CONTEXT_MESSAGES = 4
EXTENDED_CONTEXT_MESSAGES = 12

# Explicit references to earlier discussion justify the existing bounded history window.
_DISTANT_CONTEXT_REFERENCES = (
    "we discussed",
    "we talked about",
    "you mentioned earlier",
    "you told me earlier",
    "previously",
    "earlier",
    "those alternatives we discussed",
    "the requirements i gave you",
    "discutimos",
    "hablamos",
    "mencionaste antes",
    "me dijiste antes",
    "anteriormente",
    "los requisitos que te di",
)

# These are grammatical follow-up signals, not topic keywords. They conservatively retain
# only the immediately recent turns when the current utterance contains an unresolved referent.
_IMMEDIATE_CONTEXT_PHRASES = (
    "just said",
    "you just said",
    "the second one",
    "the first one",
    "acabas de decir",
    "lo que acabas de decir",
    "lo segundo",
    "lo primero",
)
_IMMEDIATE_REFERENCE_TOKENS = frozenset(
    {
        "this",
        "that",
        "these",
        "those",
        "it",
        "esto",
        "eso",
        "esta",
        "este",
        "esa",
        "ese",
        "estas",
        "estos",
        "esas",
        "esos",
        "aquello",
    }
)
_FOLLOW_UP_PREFIXES = (
    "and ",
    "but ",
    "then ",
    "so ",
    "y ",
    "pero ",
    "entonces ",
)

# Memory gating intentionally uses a compact set of explicit recall semantics plus a
# conservative personal-fact question shape. It does not attempt semantic retrieval.
_MEMORY_REFERENCE_PHRASES = (
    "remember about me",
    "remember from me",
    "what you remember",
    "what you know about me",
    "i told you",
    "we decided",
    "recuerdas de mí",
    "recuerdas sobre mí",
    "lo que recuerdas",
    "lo que sabes de mí",
    "te dije",
    "habíamos decidido",
    "habiamos decidido",
    "decidimos",
)
_MEMORY_REFERENCE_TOKENS = frozenset(
    {
        "memory",
        "memories",
        "remember",
        "remembered",
        "memoria",
        "memorias",
        "recuerdo",
        "recuerdos",
        "recuerdas",
        "recordar",
    }
)
_FIRST_PERSON_POSSESSIVES = frozenset({"my", "mi", "mis"})
_PERSONAL_FACT_QUESTION_WORDS = frozenset(
    {
        "what",
        "which",
        "how",
        "where",
        "when",
        "qué",
        "que",
        "cuál",
        "cual",
        "cuáles",
        "cuales",
        "cómo",
        "como",
        "dónde",
        "donde",
        "cuándo",
        "cuando",
    }
)

_MEDIUM_TASK_OPERATORS = (
    "analyze",
    "analyse",
    "compare",
    "contrast",
    "evaluate",
    "synthesize",
    "design",
    "debug",
    "troubleshoot",
    "review",
    "plan",
    "prioritize",
    "rank",
    "analiza",
    "compara",
    "contrasta",
    "evalúa",
    "evalua",
    "sintetiza",
    "diseña",
    "disena",
    "depura",
    "diagnostica",
    "revisa",
    "planifica",
    "prioriza",
    "ordena",
)

_HIGH_REASONING_MARKERS = (
    "rigorous",
    "exhaustive",
    "deep analysis",
    "formal proof",
    "prove formally",
    "derive step by step",
    "root cause analysis",
    "threat model",
    "arquitectura completa",
    "análisis riguroso",
    "analisis riguroso",
    "análisis exhaustivo",
    "analisis exhaustivo",
    "análisis profundo",
    "analisis profundo",
    "demuestra formalmente",
    "deriva paso a paso",
    "análisis de causa raíz",
    "analisis de causa raiz",
    "modelo de amenazas",
)

_SERVER_OUTPUT_CAP = {
    Complexity.TRIVIAL: 256,
    Complexity.LOW: 384,
    Complexity.MEDIUM: 1024,
    Complexity.HIGH: 2048,
    Complexity.VERY_HIGH: 4096,
}


def _tokens(normalized: str) -> frozenset[str]:
    return frozenset(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))


def _context_dependency(normalized: str, tokens: frozenset[str]) -> tuple[ContextDependency, int]:
    if any(marker in normalized for marker in _DISTANT_CONTEXT_REFERENCES):
        return ContextDependency.PRIOR_CONTEXT, EXTENDED_CONTEXT_MESSAGES

    leading = normalized.lstrip("¿?¡!.,;: ")
    immediate = (
        any(marker in normalized for marker in _IMMEDIATE_CONTEXT_PHRASES)
        or bool(tokens & _IMMEDIATE_REFERENCE_TOKENS)
        or any(leading.startswith(prefix) for prefix in _FOLLOW_UP_PREFIXES)
    )
    if immediate:
        return ContextDependency.PRIOR_CONTEXT, RECENT_CONTEXT_MESSAGES
    return ContextDependency.INDEPENDENT, 0


def _memory_dependency(normalized: str, tokens: frozenset[str]) -> MemoryDependency:
    if any(marker in normalized for marker in _MEMORY_REFERENCE_PHRASES):
        return MemoryDependency.NEEDED
    if tokens & _MEMORY_REFERENCE_TOKENS:
        return MemoryDependency.NEEDED

    # Questions about a fact owned by the user are conservatively memory-dependent.
    # This keeps continuity for "¿Cuál es mi color favorito?" without injecting Memory
    # into general knowledge requests such as "¿Qué es Python?".
    if tokens & _FIRST_PERSON_POSSESSIVES and tokens & _PERSONAL_FACT_QUESTION_WORDS:
        return MemoryDependency.NEEDED
    return MemoryDependency.NOT_NEEDED


def profile_chat_task(content: str, *, requested_output_tokens: int) -> ChatTaskProfile:
    """Classify current-task semantics without using available history or context size.

    Context and Memory dependency are independent from task complexity. The client-provided
    output value remains a ceiling; the server may choose a smaller budget but never enlarges it.
    """

    normalized = " ".join(content.casefold().split())
    tokens = _tokens(normalized)
    context_dependency, history_message_limit = _context_dependency(normalized, tokens)
    memory_dependency = _memory_dependency(normalized, tokens)

    has_reasoning_operator = any(operator in normalized for operator in _MEDIUM_TASK_OPERATORS)
    if has_reasoning_operator and any(marker in normalized for marker in _HIGH_REASONING_MARKERS):
        complexity = Complexity.HIGH
    elif has_reasoning_operator:
        complexity = Complexity.MEDIUM
    else:
        complexity = Complexity.LOW

    budget = min(requested_output_tokens, _SERVER_OUTPUT_CAP[complexity])
    return ChatTaskProfile(
        complexity=complexity,
        context_dependency=context_dependency,
        memory_dependency=memory_dependency,
        history_message_limit=history_message_limit,
        output_token_budget=budget,
    )
