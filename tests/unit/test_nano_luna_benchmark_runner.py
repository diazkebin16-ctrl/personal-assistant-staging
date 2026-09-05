"""Offline safety checks for the real Nano/Luna benchmark runner."""

import asyncio
from types import SimpleNamespace
from typing import Any, cast

from backend.app.ai_router.benchmark import NANO_LUNA_BENCHMARK_CASES
from backend.app.ai_router.diagnostics import ProviderResponseStatus
from scripts import run_nano_luna_benchmark as runner
from scripts.run_nano_luna_benchmark import (
    MIN_EVALUATION_OUTPUT_TOKENS,
    _evaluation_budget,
    _input_text,
    _selected_cases,
    _selected_models,
)


def test_benchmark_has_exactly_ten_small_synthetic_cases() -> None:
    assert len(NANO_LUNA_BENCHMARK_CASES) == 10
    assert max(case.output_token_budget for case in NANO_LUNA_BENCHMARK_CASES) <= 512
    assert {case.key for case in NANO_LUNA_BENCHMARK_CASES} == {
        "greeting",
        "simple_fact",
        "short_explanation",
        "rewrite",
        "intent",
        "extract",
        "short_summary",
        "recent_follow_up",
        "allowed_context",
        "strong_reasoning_boundary",
    }


def test_context_cases_embed_only_fixture_context() -> None:
    follow_up = next(case for case in NANO_LUNA_BENCHMARK_CASES if case.key == "recent_follow_up")
    rendered = _input_text(follow_up)
    assert "Contexto permitido:" in rendered
    assert "El plan cuesta 20 dólares al mes." in rendered
    assert "¿Y cuánto cuesta?" in rendered


def test_high_case_is_explicit_negative_control() -> None:
    high = next(
        case for case in NANO_LUNA_BENCHMARK_CASES if case.key == "strong_reasoning_boundary"
    )
    assert high.requires_stronger_reasoning is True


def test_evaluation_floor_is_separate_from_productive_fixture_budget() -> None:
    greeting = next(case for case in NANO_LUNA_BENCHMARK_CASES if case.key == "greeting")
    high = next(
        case for case in NANO_LUNA_BENCHMARK_CASES if case.key == "strong_reasoning_boundary"
    )
    assert greeting.output_token_budget == 128
    assert MIN_EVALUATION_OUTPUT_TOKENS == 256
    assert _evaluation_budget(greeting) == 256
    assert _evaluation_budget(high) == 512


def test_selectors_can_isolate_exactly_greeting_and_nano() -> None:
    cases = _selected_cases("greeting")
    models = _selected_models("gpt-5-nano")
    assert tuple(case.key for case in cases) == ("greeting",)
    assert models == (("gpt-5-nano", False),)


def test_single_call_ceiling_prevents_second_provider_invocation(monkeypatch: Any) -> None:
    async def scenario() -> None:
        calls = 0

        class FakeEvaluator:
            def __init__(self, *_: Any, **__: Any) -> None:
                pass

            async def evaluate(self, *_: Any, **__: Any) -> Any:
                nonlocal calls
                calls += 1
                return SimpleNamespace(
                    latency_ms=1,
                    estimated_cost_microunits=1,
                    response=SimpleNamespace(
                        reported_model_id="gpt-5-nano",
                        status=ProviderResponseStatus.COMPLETED,
                        input_tokens=1,
                        cached_tokens=0,
                        output_tokens=1,
                        reasoning_tokens=0,
                        output_text="Hola",
                        incomplete_reason=None,
                    ),
                )

        class FakeSettings:
            openai_api_key = SimpleNamespace(get_secret_value=lambda: "fixture-key")

        monkeypatch.setattr(runner, "get_settings", lambda: FakeSettings())
        monkeypatch.setattr(runner, "CandidateEvaluator", FakeEvaluator)
        monkeypatch.setattr(
            runner,
            "OpenAIProvider",
            lambda _: cast(Any, SimpleNamespace(key="openai")),
        )
        result = await runner._run(case_key="greeting", model_id="gpt-5-nano", max_calls=1)
        assert result == 0
        assert calls == 1

    asyncio.run(scenario())
