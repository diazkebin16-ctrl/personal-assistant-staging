"""Run the authorized GPT-5 Nano versus GPT-5.6 Luna benchmark.

The runner is explicit, sequential, public-data-only, and retry-free. It exits after
any non-completed provider outcome so a technical issue cannot spend additional calls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass

from backend.app.ai_router.benchmark import NANO_LUNA_BENCHMARK_CASES, BenchmarkCase
from backend.app.ai_router.catalog import build_openai_staging_catalog
from backend.app.ai_router.diagnostics import ProviderResponseStatus
from backend.app.ai_router.enums import ModelCapability
from backend.app.ai_router.evaluation import CandidateEvaluator
from backend.app.ai_router.openai_provider import OpenAIProvider
from backend.app.ai_router.provider import ProviderFailure, ProviderRegistry
from backend.app.ai_router.schemas import ModelReference, ProviderRequest, RoutingRequest
from backend.app.core.config import get_settings
from backend.app.security.classification import DataSensitivity

MIN_EVALUATION_OUTPUT_TOKENS = 256
_ALLOWED_MODELS = ("gpt-5-nano", "gpt-5.6-luna")
# CLI selectors are explicit safety controls for bounded diagnostic runs.


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    case: str
    model: str
    reported_model: str | None
    status: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    latency_ms: int
    estimated_cost_microunits: int
    output_text: str | None = None
    incomplete_reason: str | None = None


def _input_text(case: BenchmarkCase) -> str:
    if not case.prior_context:
        return case.prompt
    context = "\n".join(f"- {item}" for item in case.prior_context)
    return f"Contexto permitido:\n{context}\n\nUsuario:\n{case.prompt}"


def _evaluation_budget(case: BenchmarkCase) -> int:
    """Use an evaluation-only floor without changing productive output policy."""
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
    return parser.parse_args()


async def _run(
    *,
    case_key: str | None = None,
    model_id: str | None = None,
    max_calls: int = 20,
) -> int:
    if max_calls < 1 or max_calls > 20:
        print("BENCHMARK_ABORT max_calls must be between 1 and 20", flush=True)
        return 2

    try:
        selected_cases = _selected_cases(case_key)
        selected_models = _selected_models(model_id)
    except ValueError as exc:
        print(f"BENCHMARK_ABORT {exc}", flush=True)
        return 2

    settings = get_settings()
    if settings.openai_api_key is None:
        print("BENCHMARK_ABORT missing OPENAI_API_KEY", flush=True)
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

    provider = OpenAIProvider(settings.openai_api_key.get_secret_value())
    evaluator = CandidateEvaluator(catalog, ProviderRegistry((provider,)))
    calls = 0

    for case in selected_cases:
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

        for selected_model_id, baseline in selected_models:
            if calls >= max_calls:
                print("BENCHMARK_ABORT call ceiling reached", flush=True)
                return 2
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
                calls += 1
                print(
                    "BENCHMARK_FAILURE "
                    + json.dumps(
                        {
                            "case": case.key,
                            "model": selected_model_id,
                            "failure_category": exc.category.value,
                            "calls_attempted": calls,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                return 2

            calls += 1
            response = result.response
            row = BenchmarkResult(
                case=case.key,
                model=selected_model_id,
                reported_model=response.reported_model_id,
                status=response.status.value,
                input_tokens=response.input_tokens,
                cached_input_tokens=response.cached_tokens,
                output_tokens=response.output_tokens,
                reasoning_tokens=response.reasoning_tokens,
                latency_ms=result.latency_ms,
                estimated_cost_microunits=result.estimated_cost_microunits,
                output_text=(
                    response.output_text
                    if response.status is ProviderResponseStatus.COMPLETED
                    else None
                ),
                incomplete_reason=response.incomplete_reason,
            )
            prefix = (
                "BENCHMARK_RESULT"
                if response.status is ProviderResponseStatus.COMPLETED
                else "BENCHMARK_DIAGNOSTIC"
            )
            print(f"{prefix} " + json.dumps(asdict(row), ensure_ascii=False), flush=True)
            if response.status is not ProviderResponseStatus.COMPLETED:
                return 2

    print(json.dumps({"benchmark_complete": True, "calls": calls}), flush=True)
    return 0


def main() -> None:
    args = _parse_args()
    raise SystemExit(
        asyncio.run(
            _run(
                case_key=args.case_key,
                model_id=args.model,
                max_calls=args.max_calls,
            )
        )
    )


if __name__ == "__main__":
    main()
