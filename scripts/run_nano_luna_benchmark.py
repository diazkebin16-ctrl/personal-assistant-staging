"""Run the authorized 20-call GPT-5 Nano versus GPT-5.6 Luna benchmark.

This runner is intentionally explicit, sequential, public-data-only, and retry-free.
It exits immediately on the first provider failure so a technical error cannot trigger
extra paid calls automatically.
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict, dataclass

from backend.app.ai_router.benchmark import NANO_LUNA_BENCHMARK_CASES, BenchmarkCase
from backend.app.ai_router.catalog import build_openai_staging_catalog
from backend.app.ai_router.enums import ModelCapability
from backend.app.ai_router.evaluation import CandidateEvaluator
from backend.app.ai_router.openai_provider import OpenAIProvider
from backend.app.ai_router.provider import ProviderFailure, ProviderRegistry
from backend.app.ai_router.schemas import ModelReference, ProviderRequest, RoutingRequest
from backend.app.core.config import get_settings
from backend.app.security.classification import DataSensitivity


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    case: str
    model: str
    success: bool
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    latency_ms: int
    estimated_cost_microunits: int
    output_text: str


def _input_text(case: BenchmarkCase) -> str:
    if not case.prior_context:
        return case.prompt
    context = "\n".join(f"- {item}" for item in case.prior_context)
    return f"Contexto permitido:\n{context}\n\nUsuario:\n{case.prompt}"


def _model_ref(model_id: str) -> ModelReference:
    catalog = build_openai_staging_catalog()
    model = next(item for item in catalog.all_models if item.model_id == model_id)
    return ModelReference.from_definition(model)


async def _run() -> int:
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

    for case in NANO_LUNA_BENCHMARK_CASES:
        input_text = _input_text(case)
        routing_request = RoutingRequest(
            task_type="benchmark.nano_luna",
            complexity=case.complexity,
            required_capabilities=frozenset({ModelCapability.TEXT_GENERATION}),
            sensitivity=DataSensitivity.PUBLIC,
            estimated_input_tokens=max(1, len(input_text) // 3),
            requested_output_tokens=case.output_token_budget,
        )
        provider_request = ProviderRequest(
            input_text=input_text,
            output_token_budget=case.output_token_budget,
        )

        for model_id, baseline in (("gpt-5-nano", False), ("gpt-5.6-luna", True)):
            if calls >= 20:
                print("BENCHMARK_ABORT call ceiling reached", flush=True)
                return 2
            try:
                if baseline:
                    result = await evaluator.evaluate_routing_baseline(
                        _model_ref(model_id), routing_request, provider_request
                    )
                else:
                    result = await evaluator.evaluate(
                        _model_ref(model_id), routing_request, provider_request
                    )
            except ProviderFailure as exc:
                calls += 1
                print(
                    "BENCHMARK_FAILURE "
                    + json.dumps(
                        {
                            "case": case.key,
                            "model": model_id,
                            "failure_category": exc.category.value,
                            "calls_attempted": calls,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                return 2

            calls += 1
            row = BenchmarkResult(
                case=case.key,
                model=model_id,
                success=True,
                input_tokens=result.response.input_tokens,
                cached_input_tokens=result.response.cached_tokens,
                output_tokens=result.response.output_tokens,
                latency_ms=result.latency_ms,
                estimated_cost_microunits=result.estimated_cost_microunits,
                output_text=result.response.output_text,
            )
            print(
                "BENCHMARK_RESULT " + json.dumps(asdict(row), ensure_ascii=False),
                flush=True,
            )

    print(json.dumps({"benchmark_complete": True, "calls": calls}), flush=True)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
