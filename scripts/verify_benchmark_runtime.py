"""Verify benchmark persistence and fail-closed resume with FakeProvider only.

This administrative harness never reads model credentials and never constructs an
OpenAIProvider. It is intended to be run through ``railway ssh`` inside the
normal backend runtime where the benchmark volume is mounted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from backend.app.ai_router.benchmark import NANO_LUNA_BENCHMARK_CASES, BenchmarkCase
from backend.app.ai_router.benchmark_store import (
    BenchmarkCallRecord,
    BenchmarkResultStore,
    BenchmarkRunDocument,
    BenchmarkStoreError,
    CheckpointState,
)
from backend.app.ai_router.catalog import build_openai_staging_catalog
from backend.app.ai_router.diagnostics import ProviderResponseStatus
from backend.app.ai_router.enums import ModelCapability
from backend.app.ai_router.evaluation import CandidateEvaluator
from backend.app.ai_router.provider import FakeProvider, ProviderRegistry
from backend.app.ai_router.schemas import (
    ModelReference,
    ProviderRequest,
    ProviderResponse,
    RoutingRequest,
)
from backend.app.security.classification import DataSensitivity

_FAKE_MODEL_ID = "gpt-5-nano"
_FAKE_OUTPUT = "FAKE_PROVIDER_OK"


def _case(case_id: str) -> BenchmarkCase:
    return next(case for case in NANO_LUNA_BENCHMARK_CASES if case.key == case_id)


def _model_ref() -> ModelReference:
    catalog = build_openai_staging_catalog()
    model = next(model for model in catalog.all_models if model.model_id == _FAKE_MODEL_ID)
    return ModelReference.from_definition(model)


def _input_text(case: BenchmarkCase) -> str:
    if not case.prior_context:
        return case.prompt
    context = "\n".join(f"- {item}" for item in case.prior_context)
    return f"Contexto permitido:\n{context}\n\nUsuario:\n{case.prompt}"


def _started(run_id: str, case_id: str) -> BenchmarkCallRecord:
    return BenchmarkCallRecord(
        benchmark_run_id=run_id,
        case_id=case_id,
        requested_model=_FAKE_MODEL_ID,
        checkpoint_state=CheckpointState.IN_PROGRESS,
        timestamp=datetime.now(UTC),
    )


def _finished(
    run_id: str,
    case_id: str,
    *,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    latency_ms: int,
    estimated_cost_microunits: int,
) -> BenchmarkCallRecord:
    return BenchmarkCallRecord(
        benchmark_run_id=run_id,
        case_id=case_id,
        requested_model=_FAKE_MODEL_ID,
        reported_model=_FAKE_MODEL_ID,
        checkpoint_state=CheckpointState.FINISHED,
        normalized_status=ProviderResponseStatus.COMPLETED,
        succeeded=True,
        input_tokens=input_tokens,
        cached_input_tokens=cached_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=0,
        latency_ms=latency_ms,
        estimated_cost_microunits=estimated_cost_microunits,
        output_text=_FAKE_OUTPUT,
        timestamp=datetime.now(UTC),
    )


async def _complete_fake_call(
    store: BenchmarkResultStore,
    document: BenchmarkRunDocument,
    case: BenchmarkCase,
) -> tuple[BenchmarkRunDocument, int]:
    document = store.checkpoint(document, _started(document.benchmark_run_id, case.key))
    provider = FakeProvider(
        "openai",
        (
            ProviderResponse(
                output_text=_FAKE_OUTPUT,
                input_tokens=12,
                cached_tokens=4,
                output_tokens=3,
            ),
        ),
    )
    evaluator = CandidateEvaluator(
        build_openai_staging_catalog(),
        ProviderRegistry((provider,)),
    )
    input_text = _input_text(case)
    output_budget = max(256, case.output_token_budget)
    routing_request = RoutingRequest(
        task_type="benchmark.runtime_verification",
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
    result = await evaluator.evaluate(_model_ref(), routing_request, provider_request)
    response = result.response
    if response.status is not ProviderResponseStatus.COMPLETED:
        raise RuntimeError("FakeProvider verification did not complete")
    document = store.checkpoint(
        document,
        _finished(
            document.benchmark_run_id,
            case.key,
            input_tokens=response.input_tokens,
            cached_tokens=response.cached_tokens,
            output_tokens=response.output_tokens,
            latency_ms=result.latency_ms,
            estimated_cost_microunits=result.estimated_cost_microunits,
        ),
    )
    return document, provider.call_count


async def _run_complete(result_dir: Path, run_id: str) -> int:
    store = BenchmarkResultStore(result_dir)
    try:
        document = store.create(run_id)
        document, provider_calls = await _complete_fake_call(store, document, _case("greeting"))
    except (BenchmarkStoreError, RuntimeError) as exc:
        print(
            json.dumps({"status": "failed", "reason": type(exc).__name__}),
            flush=True,
        )
        return 2
    print(
        json.dumps(
            {
                "status": "completed",
                "run_id": run_id,
                "provider": "FakeProvider",
                "provider_calls": provider_calls,
                "openai_calls": 0,
                "attempted_calls": document.aggregates.attempted_calls,
                "finished_calls": document.aggregates.finished_calls,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


async def _run_crash(result_dir: Path, run_id: str) -> int:
    """Persist one finished fake call plus one ambiguous in-progress checkpoint."""
    store = BenchmarkResultStore(result_dir)
    try:
        document = store.create(run_id)
        document, provider_calls = await _complete_fake_call(store, document, _case("greeting"))
        document = store.checkpoint(document, _started(run_id, "simple_fact"))
    except (BenchmarkStoreError, RuntimeError) as exc:
        print(
            json.dumps({"status": "failed", "reason": type(exc).__name__}),
            flush=True,
        )
        return 2
    print(
        json.dumps(
            {
                "status": "simulated_crash_checkpointed",
                "run_id": run_id,
                "provider": "FakeProvider",
                "provider_calls": provider_calls,
                "openai_calls": 0,
                "attempted_calls": document.aggregates.attempted_calls,
                "finished_calls": document.aggregates.finished_calls,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


def _run_resume(result_dir: Path, run_id: str) -> int:
    """Prove resume fails closed without constructing or invoking any provider."""
    store = BenchmarkResultStore(result_dir)
    try:
        document = store.load(run_id)
    except BenchmarkStoreError as exc:
        print(
            json.dumps({"status": "failed", "reason": type(exc).__name__}),
            flush=True,
        )
        return 2
    ambiguous = tuple(
        call for call in document.calls if call.checkpoint_state is CheckpointState.IN_PROGRESS
    )
    if not ambiguous:
        print(
            json.dumps({"status": "failed", "reason": "no_in_progress_checkpoint"}),
            flush=True,
        )
        return 2
    print(
        json.dumps(
            {
                "status": "resume_refused_fail_closed",
                "run_id": run_id,
                "ambiguous_case_ids": [call.case_id for call in ambiguous],
                "provider_calls": 0,
                "openai_calls": 0,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("complete", "crash", "resume"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.mode == "complete":
        raise SystemExit(asyncio.run(_run_complete(args.result_dir, args.run_id)))
    if args.mode == "crash":
        raise SystemExit(asyncio.run(_run_crash(args.result_dir, args.run_id)))
    raise SystemExit(_run_resume(args.result_dir, args.run_id))


if __name__ == "__main__":
    main()
