"""Offline safety checks for the real Nano/Luna benchmark runner."""

from backend.app.ai_router.benchmark import NANO_LUNA_BENCHMARK_CASES
from scripts.run_nano_luna_benchmark import _input_text


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
