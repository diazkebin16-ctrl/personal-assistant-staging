"""Task complexity and response-budget regressions for conversational routing."""

from uuid import uuid4

import pytest

from backend.app.ai_router.catalog import build_staging_catalog
from backend.app.ai_router.enums import Complexity
from backend.app.ai_router.policy import AIRoutingPolicy
from backend.app.ai_router.schemas import RoutingRequest
from backend.app.security.classification import DataSensitivity
from backend.app.text_assistant.task_profile import ContextDependency, profile_chat_task


def test_simple_questions_are_low_complexity() -> None:
    for content in (
        "¿Qué puedes hacer?",
        "¿Conoces a Microsoft?",
        "Explícame qué es una API.",
    ):
        profile = profile_chat_task(content, requested_output_tokens=1024)
        assert profile.complexity is Complexity.LOW
        assert profile.context_dependency is ContextDependency.INDEPENDENT


def test_history_dependent_simple_question_stays_low() -> None:
    profile = profile_chat_task(
        "¿Qué me dijiste antes sobre eso?",
        requested_output_tokens=1024,
    )
    assert profile.complexity is Complexity.LOW
    assert profile.context_dependency is ContextDependency.PRIOR_CONTEXT


def test_comparison_over_prior_requirements_is_medium_and_context_dependent() -> None:
    profile = profile_chat_task(
        "Compara las tres alternativas que discutimos y determina cuál cumple mejor "
        "los requisitos que te di.",
        requested_output_tokens=2048,
    )
    assert profile.complexity is Complexity.MEDIUM
    assert profile.context_dependency is ContextDependency.PRIOR_CONTEXT
    assert profile.output_token_budget == 1024


def test_explicit_deep_reasoning_can_still_be_high() -> None:
    profile = profile_chat_task(
        "Haz un análisis riguroso y compara las alternativas con sus tradeoffs.",
        requested_output_tokens=4096,
    )
    assert profile.complexity is Complexity.HIGH
    assert profile.output_token_budget == 2048


def test_simple_output_budget_is_lower_without_expanding_client_ceiling() -> None:
    simple = profile_chat_task("¿Qué puedes hacer?", requested_output_tokens=1024)
    complex_task = profile_chat_task(
        "Compara estas opciones y evalúa sus riesgos.",
        requested_output_tokens=1024,
    )
    assert simple.output_token_budget == 384
    assert complex_task.output_token_budget == 1024


def test_high_complexity_keeps_larger_requested_budget_when_justified() -> None:
    profile = profile_chat_task(
        "Haz un análisis profundo y compara cada alternativa rigurosamente.",
        requested_output_tokens=2048,
    )
    assert profile.complexity is Complexity.HIGH
    assert profile.output_token_budget == 2048


def test_server_never_increases_requested_output_ceiling() -> None:
    profile = profile_chat_task(
        "Haz un análisis profundo y compara cada alternativa rigurosamente.",
        requested_output_tokens=600,
    )
    assert profile.output_token_budget == 600


@pytest.mark.parametrize(
    ("complexity", "expected_model"),
    [
        (Complexity.LOW, "gpt-5.6-luna"),
        (Complexity.MEDIUM, "gpt-5.6-terra"),
        (Complexity.HIGH, "gpt-5.6-sol"),
    ],
)
def test_openai_complexity_tiers_remain_available(
    complexity: Complexity,
    expected_model: str,
) -> None:
    catalog = build_staging_catalog(openai_enabled=True, gemini_enabled=True)
    decision = AIRoutingPolicy(catalog).decide(
        uuid4(),
        RoutingRequest(
            task_type="text_assistant.conversation",
            complexity=complexity,
            sensitivity=DataSensitivity.PUBLIC,
            estimated_input_tokens=100,
            requested_output_tokens=384,
        ),
    )
    assert decision.selected_model is not None
    assert decision.selected_model.model_id == expected_model
    assert all(item.provider_key != "gemini" for item in decision.fallback_chain)
