"""Offline safety and persistence checks for the Nano/Luna benchmark runner."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from backend.app.ai_router.benchmark import NANO_LUNA_BENCHMARK_CASES
from backend.app.ai_router.benchmark_store import (
    BenchmarkCallRecord,
    BenchmarkResultStore,
    BenchmarkStoreError,
    CheckpointState,
)
from backend.app.ai_router.catalog import build_openai_staging_catalog
from backend.app.ai_router.diagnostics import ProviderDiagnosticResponse, ProviderResponseStatus
from backend.app.ai_router.enums import FailureCategory, ModelClass
from backend.app.ai_router.provider import ProviderFailure
from scripts import run_nano_luna_benchmark as runner
from scripts.run_nano_luna_benchmark import (
    MIN_EVALUATION_OUTPUT_TOKENS,
    _evaluation_budget,
    _input_text,
    _selected_cases,
    _selected_models,
)


def _settings() -> Any:
    return SimpleNamespace(
        openai_api_key=SimpleNamespace(get_secret_value=lambda: "fixture-secret-key")
    )


def _result(
    status: ProviderResponseStatus = ProviderResponseStatus.COMPLETED,
    *,
    output_text: str = "Hola",
    incomplete_reason: str | None = None,
    input_tokens: int = 11,
    cached_tokens: int = 3,
    output_tokens: int = 7,
    reasoning_tokens: int = 2,
    latency_ms: int = 123,
    estimated_cost_microunits: int = 456,
) -> Any:
    return SimpleNamespace(
        latency_ms=latency_ms,
        estimated_cost_microunits=estimated_cost_microunits,
        response=ProviderDiagnosticResponse(
            status=status,
            reported_model_id="gpt-5-nano-2026-08-07",
            output_text=output_text,
            incomplete_reason=incomplete_reason,
            input_tokens=input_tokens,
            cached_tokens=cached_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
        ),
    )


def _install_fakes(monkeypatch: Any, evaluator: Any) -> None:
    monkeypatch.setattr(runner, "get_settings", _settings)
    monkeypatch.setattr(runner, "CandidateEvaluator", lambda *_args, **_kwargs: evaluator)
    monkeypatch.setattr(
        runner,
        "OpenAIProvider",
        lambda _: cast(Any, SimpleNamespace(key="openai")),
    )


def _run(
    tmp_path: Path,
    monkeypatch: Any,
    evaluator: Any,
    *,
    run_id: str = "run-a",
    case_key: str | None = "greeting",
    model_id: str | None = "gpt-5-nano",
    max_calls: int = 1,
    resume: bool = False,
) -> int:
    _install_fakes(monkeypatch, evaluator)
    return asyncio.run(
        runner._run(
            case_key=case_key,
            model_id=model_id,
            max_calls=max_calls,
            run_id=run_id,
            result_dir=tmp_path,
            resume=resume,
        )
    )


class SequenceEvaluator:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    async def _next(self) -> Any:
        index = self.calls
        self.calls += 1
        outcome = self.outcomes[index]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def evaluate(self, *_: Any, **__: Any) -> Any:
        return await self._next()

    async def evaluate_routing_baseline(self, *_: Any, **__: Any) -> Any:
        return await self._next()


def test_benchmark_has_exactly_ten_small_synthetic_cases() -> None:
    assert len(NANO_LUNA_BENCHMARK_CASES) == 10
    assert max(case.output_token_budget for case in NANO_LUNA_BENCHMARK_CASES) <= 512


def test_context_rendering_remains_fixture_only() -> None:
    follow_up = next(case for case in NANO_LUNA_BENCHMARK_CASES if case.key == "recent_follow_up")
    rendered = _input_text(follow_up)
    assert "Contexto permitido:" in rendered
    assert "El plan cuesta 20 dólares al mes." in rendered
    assert "¿Y cuánto cuesta?" in rendered


def test_evaluation_floor_and_selectors_are_preserved() -> None:
    greeting = next(case for case in NANO_LUNA_BENCHMARK_CASES if case.key == "greeting")
    assert greeting.output_token_budget == 128
    assert MIN_EVALUATION_OUTPUT_TOKENS == 1024
    assert _evaluation_budget(greeting) == 1024
    assert tuple(case.key for case in _selected_cases("greeting")) == ("greeting",)
    assert _selected_models("gpt-5-nano") == (("gpt-5-nano", False),)


def test_completed_persists_full_scoring_metadata_without_prompt_or_credentials(
    tmp_path: Path, monkeypatch: Any
) -> None:
    evaluator = SequenceEvaluator([_result()])
    assert _run(tmp_path, monkeypatch, evaluator) == 0

    document = BenchmarkResultStore(tmp_path).load("run-a")
    call = document.calls[0]
    assert call.normalized_status is ProviderResponseStatus.COMPLETED
    assert call.succeeded is True
    assert call.reported_model == "gpt-5-nano-2026-08-07"
    assert call.input_tokens == 11
    assert call.cached_input_tokens == 3
    assert call.output_tokens == 7
    assert call.reasoning_tokens == 2
    assert call.latency_ms == 123
    assert call.estimated_cost_microunits == 456
    assert call.output_text == "Hola"
    assert document.aggregates.attempted_calls == 1
    assert document.aggregates.estimated_cost_microunits == 456

    raw = (tmp_path / "run-a" / "result.json").read_text(encoding="utf-8")
    assert "Hola, ¿cómo estás?" not in raw
    assert "fixture-secret-key" not in raw
    assert "OPENAI_API_KEY" not in raw


def test_incomplete_persists_usage_and_reason(tmp_path: Path, monkeypatch: Any) -> None:
    evaluator = SequenceEvaluator(
        [
            _result(
                ProviderResponseStatus.INCOMPLETE,
                output_text="",
                incomplete_reason="max_output_tokens",
            )
        ]
    )
    assert _run(tmp_path, monkeypatch, evaluator) == 2
    call = BenchmarkResultStore(tmp_path).load("run-a").calls[0]
    assert call.normalized_status is ProviderResponseStatus.INCOMPLETE
    assert call.incomplete_reason == "max_output_tokens"
    assert call.input_tokens == 11
    assert call.output_tokens == 7


def test_malformed_persists(tmp_path: Path, monkeypatch: Any) -> None:
    evaluator = SequenceEvaluator([_result(ProviderResponseStatus.MALFORMED, output_text="")])
    assert _run(tmp_path, monkeypatch, evaluator) == 2
    call = BenchmarkResultStore(tmp_path).load("run-a").calls[0]
    assert call.normalized_status is ProviderResponseStatus.MALFORMED
    assert call.succeeded is False


def test_provider_error_is_sanitized_and_retry_free(tmp_path: Path, monkeypatch: Any) -> None:
    evaluator = SequenceEvaluator([ProviderFailure(FailureCategory.TIMEOUT)])
    assert _run(tmp_path, monkeypatch, evaluator) == 2
    assert evaluator.calls == 1
    call = BenchmarkResultStore(tmp_path).load("run-a").calls[0]
    assert call.normalized_status is ProviderResponseStatus.PROVIDER_ERROR
    assert call.failure_category == FailureCategory.TIMEOUT.value
    raw = (tmp_path / "run-a" / "result.json").read_text(encoding="utf-8")
    assert "fixture-secret-key" not in raw
    assert "Traceback" not in raw


def test_checkpoint_after_each_call_and_two_calls_do_not_mix(
    tmp_path: Path, monkeypatch: Any
) -> None:
    evaluator = SequenceEvaluator([_result(), _result()])
    assert (
        _run(
            tmp_path,
            monkeypatch,
            evaluator,
            model_id=None,
            max_calls=2,
        )
        == 0
    )
    document = BenchmarkResultStore(tmp_path).load("run-a")
    assert len(document.calls) == 2
    assert document.aggregates.attempted_calls == 2
    assert {call.requested_model for call in document.calls} == {
        "gpt-5-nano",
        "gpt-5.6-luna",
    }


def test_failure_on_call_n_preserves_prior_results_and_marks_n_in_progress(
    tmp_path: Path, monkeypatch: Any
) -> None:
    evaluator = SequenceEvaluator([_result(), RuntimeError("synthetic crash")])
    _install_fakes(monkeypatch, evaluator)
    with pytest.raises(RuntimeError, match="synthetic crash"):
        asyncio.run(
            runner._run(
                case_key="greeting",
                model_id=None,
                max_calls=2,
                run_id="run-a",
                result_dir=tmp_path,
            )
        )
    document = BenchmarkResultStore(tmp_path).load("run-a")
    assert document.calls[0].checkpoint_state is CheckpointState.FINISHED
    assert document.calls[0].succeeded is True
    assert document.calls[1].checkpoint_state is CheckpointState.IN_PROGRESS


def test_resume_never_repeats_finished_call(tmp_path: Path, monkeypatch: Any) -> None:
    first = SequenceEvaluator([_result()])
    assert _run(tmp_path, monkeypatch, first) == 0
    second = SequenceEvaluator([])
    assert _run(tmp_path, monkeypatch, second, resume=True) == 0
    assert second.calls == 0


def test_resume_refuses_ambiguous_in_progress_checkpoint(tmp_path: Path, monkeypatch: Any) -> None:
    store = BenchmarkResultStore(tmp_path)
    document = store.create("run-a")
    document = store.checkpoint(
        document,
        BenchmarkCallRecord(
            benchmark_run_id="run-a",
            case_id="greeting",
            requested_model="gpt-5-nano",
            checkpoint_state=CheckpointState.IN_PROGRESS,
            timestamp=datetime(2026, 9, 5, 11, 0, tzinfo=UTC),
        ),
    )
    assert document.aggregates.attempted_calls == 1
    evaluator = SequenceEvaluator([])
    assert _run(tmp_path, monkeypatch, evaluator, resume=True) == 2
    assert evaluator.calls == 0


def test_max_calls_is_absolute_across_resume(tmp_path: Path, monkeypatch: Any) -> None:
    first = SequenceEvaluator([_result()])
    assert _run(tmp_path, monkeypatch, first, max_calls=1) == 0
    second = SequenceEvaluator([])
    assert (
        _run(
            tmp_path,
            monkeypatch,
            second,
            case_key=None,
            model_id="gpt-5-nano",
            max_calls=1,
            resume=True,
        )
        == 2
    )
    assert second.calls == 0


def test_two_run_ids_are_isolated(tmp_path: Path) -> None:
    store = BenchmarkResultStore(tmp_path)
    first = store.create("run-a")
    second = store.create("run-b")
    assert first.benchmark_run_id == "run-a"
    assert second.benchmark_run_id == "run-b"
    assert (tmp_path / "run-a" / "result.json").exists()
    assert (tmp_path / "run-b" / "result.json").exists()


def test_corrupt_checkpoint_fails_closed(tmp_path: Path) -> None:
    store = BenchmarkResultStore(tmp_path)
    store.create("run-a")
    (tmp_path / "run-a" / "result.json").write_text("{partial", encoding="utf-8")
    with pytest.raises(BenchmarkStoreError, match="missing or corrupt"):
        store.load("run-a")


def test_stray_partial_temp_file_does_not_replace_valid_checkpoint(tmp_path: Path) -> None:
    store = BenchmarkResultStore(tmp_path)
    original = store.create("run-a")
    (tmp_path / "run-a" / ".result.json.partial.tmp").write_text("garbage", encoding="utf-8")
    loaded = store.load("run-a")
    assert loaded == original


def test_existing_run_requires_explicit_resume(tmp_path: Path, monkeypatch: Any) -> None:
    evaluator = SequenceEvaluator([_result()])
    assert _run(tmp_path, monkeypatch, evaluator) == 0
    duplicate = SequenceEvaluator([])
    assert _run(tmp_path, monkeypatch, duplicate) == 2
    assert duplicate.calls == 0


def test_nano_remains_evaluation_only_and_fast_productive_remains_luna() -> None:
    catalog = build_openai_staging_catalog()
    nano = next(model for model in catalog.all_models if model.model_id == "gpt-5-nano")
    fast_routable = tuple(
        model
        for model in catalog.models
        if model.model_class is ModelClass.FAST and model.routing_enabled
    )
    assert nano.routing_enabled is False
    assert nano.evaluation_enabled is True
    assert tuple(model.model_id for model in fast_routable) == ("gpt-5.6-luna",)


def test_persisted_schema_contains_no_prompt_or_secret_fields(tmp_path: Path) -> None:
    BenchmarkResultStore(tmp_path).create("run-a")
    payload = json.loads((tmp_path / "run-a" / "result.json").read_text(encoding="utf-8"))
    serialized_keys = json.dumps(payload, sort_keys=True)
    assert "prompt" not in serialized_keys
    assert "credential" not in serialized_keys
    assert "api_key" not in serialized_keys
