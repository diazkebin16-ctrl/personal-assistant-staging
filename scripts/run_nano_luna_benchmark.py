"""Run the explicit Nano/Luna benchmark with durable, retry-free checkpoints."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from backend.app.ai_router.benchmark import NANO_LUNA_BENCHMARK_CASES, BenchmarkCase
from backend.app.ai_router.benchmark_store import (
    BENCHMARK_VERSION,
    BenchmarkCallRecord,
    BenchmarkResultStore,
    BenchmarkStoreError,
    CheckpointState,
)
from backend.app.ai_router.catalog import build_openai_staging_catalog
from backend.app.ai_router.diagnostics import ProviderResponseStatus
from backend.app.ai_router.enums import ModelCapability
from backend.app.ai_router.evaluation import CandidateEvaluator
from backend.app.ai_router.openai_provider import OpenAIProvider
from backend.app.ai_router.provider import ProviderFailure, ProviderRegistry
from backend.app.ai_router.schemas import ModelReference, ProviderRequest, RoutingRequest
from backend.app.core.config import get_settings
from backend.app.security.classification import DataSensitivity

MIN_EVALUATION_OUTPUT_TOKENS = 1024
_ALLOWED_MODELS = ("gpt-5-nano", "gpt-5.6-luna")


def _input_text(case: BenchmarkCase) -> str:
    if not case.prior_context:
        return case.prompt
    context = "\n".join(f"- {item}" for item in case.prior_context)
    return f"Contexto permitido:\n{context}\n\nUsuario:\n{case.prompt}"


def _evaluation_budget(case: BenchmarkCase) -> int:
    return max(MIN_EVALUATION_OUTPUT_TOKENS, case.output_token_budget)


def _model_ref(model_id: str) -> ModelReference:
    catalog = build_openai_staging_catalog()
    model = next(item for item in catalog.all_models if item.model_id == model_id)
    return ModelReference.from_definition(model)


def _selected_cases(case_key: str | None) -> tuple[BenchmarkCase, ...]:
    if case_key is None:
        return NANO_LUNA_BENCHMARK_CASES
    selected = tuple(case for case in NANO_LUNA_BENCHMARK_CASES if case.key == case_key)
    if len(selected) != 1:
        raise ValueError(f"Unknown benchmark case: {case_key}")
    return selected


def _selected_models(model_id: str | None) -> tuple[tuple[str, bool], ...]:
    if model_id is None:
        return (("gpt-5-nano", False), ("gpt-5.6-luna", True))
    if model_id not in _ALLOWED_MODELS:
        raise ValueError(f"Unsupported benchmark model: {model_id}")
    return ((model_id, model_id == "gpt-5.6-luna"),)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", dest="case_key")
    parser.add_argument("--model", choices=_ALLOWED_MODELS)
    parser.add_argument("--max-calls", type=int, default=20)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def _started_record(run_id: str, case_id: str, model_id: str) -> BenchmarkCallRecord:
    return BenchmarkCallRecord(
        benchmark_run_id=run_id,
        case_id=case_id,
        requested_model=model_id,
        checkpoint_state=CheckpointState.IN_PROGRESS,
        timestamp=datetime.now(UTC),
    )


def _finished_record(
    *,
    run_id: str,
    case_id: str,
    model_id: str,
    status: ProviderResponseStatus,
    reported_model: str | None = None,
    incomplete_reason: str | None = None,
    input_tokens: int = 0,
    cached_input_tokens: int = 0,
    output_tokens: int = 0,
    reasoning_tokens: int = 0,
    latency_ms: int = 0,
    estimated_cost_microunits: int = 0,
    output_text: str | None = None,
    failure_category: str | None = None,
) -> BenchmarkCallRecord:
    return BenchmarkCallRecord(
        benchmark_run_id=run_id,
        case_id=case_id,
        requested_model=model_id,
        reported_model=reported_model,
        checkpoint_state=CheckpointState.FINISHED,
        normalized_status=status,
        incomplete_reason=incomplete_reason,
        succeeded=status is ProviderResponseStatus.COMPLETED,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        latency_ms=latency_ms,
        estimated_cost_microunits=estimated_cost_microunits,
        output_text=output_text,
        failure_category=failure_category,
        timestamp=datetime.now(UTC),
    )


async def _run(
    *,
    case_key: str | None = None,
    model_id: str | None = None,
    max_calls: int = 20,
    run_id: str,
    result_dir: Path,
    resume: bool = False,
) -> int:
    if max_calls < 1 or max_calls > 20:
        print("BENCHMARK_ABORT max_calls must be between 1 and 20", flush=True)
        return 2

    try:
        selected_cases = _selected_cases(case_key)
        selected_models = _selected_models(model_id)
        store = BenchmarkResultStore(result_dir)
        document = store.load(run_id) if resume else store.create(run_id)
    except (ValueError, BenchmarkStoreError) as exc:
        print(f"BENCHMARK_ABORT {exc}", flush=True)
        return 2

    catalog = build_openai_staging_catalog()
    nano = catalog.model(_model_ref("gpt-5-nano"))
    luna = catalog.model(_model_ref("gpt-5.6-luna"))
    if nano.routing_enabled or not nano.evaluation_enabled:
        print("BENCHMARK_ABORT Nano is not evaluation-only", flush=True)
        return 2
    if not luna.routing_enabled:
        print("BENCHMARK_ABORT Luna is not routable", flush=True)
        return 2
    if len(NANO_LUNA_BENCHMARK_CASES) != 10:
        print("BENCHMARK_ABORT expected exactly 10 fixtures", flush=True)
        return 2

    selected_pairs = tuple(
        (case, selected_model_id, baseline)
        for case in selected_cases
        for selected_model_id, baseline in selected_models
    )
    pending: list[tuple[BenchmarkCase, str, bool]] = []
    for case, selected_model_id, baseline in selected_pairs:
        existing = document.record_for(case.key, selected_model_id)
        if existing is None:
            pending.append((case, selected_model_id, baseline))
            continue
        if existing.checkpoint_state is CheckpointState.IN_PROGRESS:
            print(
                "BENCHMARK_ABORT ambiguous in-progress checkpoint; refusing duplicate call",
                flush=True,
            )
            return 2
        # Finished outcomes are immutable and are never repeated by --resume.

    if not pending:
        print(
            json.dumps(
                {
                    "benchmark_complete": True,
                    "benchmark_version": BENCHMARK_VERSION,
                    "run_id": run_id,
                    "calls": document.aggregates.attempted_calls,
                }
            ),
            flush=True,
        )
        return 0

    if document.aggregates.attempted_calls >= max_calls:
        print("BENCHMARK_ABORT call ceiling reached", flush=True)
        return 2

    settings = get_settings()
    if settings.openai_api_key is None:
        print("BENCHMARK_ABORT missing OPENAI_API_KEY", flush=True)
        return 2

    provider = OpenAIProvider(settings.openai_api_key.get_secret_value())
    evaluator = CandidateEvaluator(catalog, ProviderRegistry((provider,)))

    for case, selected_model_id, baseline in pending:
        if document.aggregates.attempted_calls >= max_calls:
            print("BENCHMARK_ABORT call ceiling reached", flush=True)
            return 2

        input_text = _input_text(case)
        output_budget = _evaluation_budget(case)
        routing_request = RoutingRequest(
            task_type="benchmark.nano_luna",
            complexity=case.complexity,
            required_capabilities=frozenset({ModelCapability.TEXT_GENERATION}),
            sensitivity=DataSensitivity.PUBLIC,
            estimated_input_tokens=max(1, len(input_text) // 3),
            requested_output_tokens=output_budget,
        )
        provider_request = ProviderRequest(
            input_text=input_text,
            output_token_budget=output_budget,
        )

        try:
            document = store.checkpoint(
                document,
                _started_record(run_id, case.key, selected_model_id),
            )
        except BenchmarkStoreError as exc:
            print(f"BENCHMARK_ABORT {exc}", flush=True)
            return 2

        started = perf_counter()
        try:
            if baseline:
                result = await evaluator.evaluate_routing_baseline(
                    _model_ref(selected_model_id), routing_request, provider_request
                )
            else:
                result = await evaluator.evaluate(
                    _model_ref(selected_model_id), routing_request, provider_request
                )
        except ProviderFailure as exc:
            latency_ms = max(0, round((perf_counter() - started) * 1000))
            document = store.checkpoint(
                document,
                _finished_record(
                    run_id=run_id,
                    case_id=case.key,
                    model_id=selected_model_id,
                    status=ProviderResponseStatus.PROVIDER_ERROR,
                    latency_ms=latency_ms,
                    failure_category=exc.category.value,
                ),
            )
            print("BENCHMARK_FAILURE provider_error", flush=True)
            return 2

        response = result.response
        document = store.checkpoint(
            document,
            _finished_record(
                run_id=run_id,
                case_id=case.key,
                model_id=selected_model_id,
                status=response.status,
                reported_model=response.reported_model_id,
                incomplete_reason=response.incomplete_reason,
                input_tokens=response.input_tokens,
                cached_input_tokens=response.cached_tokens,
                output_tokens=response.output_tokens,
                reasoning_tokens=response.reasoning_tokens,
                latency_ms=result.latency_ms,
                estimated_cost_microunits=result.estimated_cost_microunits,
                output_text=response.output_text or None,
            ),
        )
        if response.status is not ProviderResponseStatus.COMPLETED:
            print(f"BENCHMARK_DIAGNOSTIC {response.status.value}", flush=True)
            return 2

    print(
        json.dumps(
            {
                "benchmark_complete": True,
                "benchmark_version": BENCHMARK_VERSION,
                "run_id": run_id,
                "calls": document.aggregates.attempted_calls,
            }
        ),
        flush=True,
    )
    return 0


def main() -> None:
    args = _parse_args()
    raise SystemExit(
        asyncio.run(
            _run(
                case_key=args.case_key,
                model_id=args.model,
                max_calls=args.max_calls,
                run_id=args.run_id,
                result_dir=args.result_dir,
                resume=args.resume,
            )
        )
    )


if __name__ == "__main__":
    main()
