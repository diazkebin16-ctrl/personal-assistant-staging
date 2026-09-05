"""Semantic chat task profiling independent of conversation size."""

from dataclasses import dataclass
from enum import StrEnum

from backend.app.ai_router.enums import Complexity


class ContextDependency(StrEnum):
    """Whether the current request explicitly depends on prior conversation context."""

    INDEPENDENT = "INDEPENDENT"
    PRIOR_CONTEXT = "PRIOR_CONTEXT"


@dataclass(frozen=True, slots=True)
class ChatTaskProfile:
    """Server-owned task semantics used for routing and bounded response budgets."""

    complexity: Complexity
    context_dependency: ContextDependency
    output_token_budget: int


_CONTEXT_REFERENCES = (
    "we discussed",
    "we talked about",
    "you mentioned",
    "you told me",
    "earlier",
    "previously",
    "above",
    "those alternatives",
    "those options",
    "discutimos",
    "hablamos",
    "mencionaste",
    "me dijiste",
    "antes",
    "anteriormente",
    "arriba",
    "esas alternativas",
    "esas opciones",
    "los requisitos que te di",
    "the requirements i gave you",
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


def profile_chat_task(content: str, *, requested_output_tokens: int) -> ChatTaskProfile:
    """Classify the current task without using available history or context size.

    The client-provided output value remains a ceiling. The server may choose a smaller
    budget for simple tasks, but never enlarges what the caller requested.
    """

    normalized = " ".join(content.casefold().split())
    dependency = (
        ContextDependency.PRIOR_CONTEXT
        if any(marker in normalized for marker in _CONTEXT_REFERENCES)
        else ContextDependency.INDEPENDENT
    )

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
        context_dependency=dependency,
        output_token_budget=budget,
    )
