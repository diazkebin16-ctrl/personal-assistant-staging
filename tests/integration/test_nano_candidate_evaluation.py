"""Offline Nano-versus-Luna evaluation through the shared OpenAI provider boundary."""

import asyncio

from backend.app.ai_router.catalog import ModelCatalog, build_staging_catalog
from backend.app.ai_router.enums import Complexity, FailureCategory, ModelCapability
from backend.app.ai_router.evaluation import CandidateEvaluator
from backend.app.ai_router.provider import FakeProvider, ProviderRegistry
from backend.app.ai_router.schemas import (
    ModelReference,
    ProviderRequest,
    ProviderResponse,
    RoutingRequest,
)
from backend.app.security.classification import DataSensitivity


def _ref(catalog: ModelCatalog, model_id: str) -> ModelReference:
    model = next(item for item in catalog.all_models if item.model_id == model_id)
    return ModelReference.from_definition(model)


def _routing_request() -> RoutingRequest:
    return RoutingRequest(
        task_type="assistant.response",
        complexity=Complexity.LOW,
        required_capabilities=frozenset({ModelCapability.TEXT_GENERATION}),
        sensitivity=DataSensitivity.PRIVATE,
        estimated_input_tokens=100,
        requested_output_tokens=64,
    )


def _provider_request() -> ProviderRequest:
    return ProviderRequest(input_text="offline fixture", output_token_budget=64)


def test_candidate_and_luna_baseline_share_openai_adapter_and_cached_accounting() -> None:
    async def scenario() -> None:
        catalog = build_staging_catalog(openai_enabled=True)
        provider = FakeProvider(
            "openai",
            outcomes=(
                ProviderResponse(
                    output_text="nano answer",
                    input_tokens=100,
                    output_tokens=20,
                    cached_tokens=40,
                ),
                ProviderResponse(
                    output_text="luna answer",
                    input_tokens=100,
                    output_tokens=20,
                    cached_tokens=40,
                ),
            ),
        )
        evaluator = CandidateEvaluator(catalog, ProviderRegistry((provider,)))
        nano = await evaluator.evaluate(
            _ref(catalog, "gpt-5-nano"), _routing_request(), _provider_request()
        )
        luna = await evaluator.evaluate_routing_baseline(
            _ref(catalog, "gpt-5.6-luna"), _routing_request(), _provider_request()
        )
        assert nano.response.output_text == "nano answer"
        assert nano.response.cached_tokens == 40
        assert nano.estimated_cost_microunits == 12
        assert luna.response.output_text == "luna answer"
        assert provider.call_count == 2

    asyncio.run(scenario())


def test_candidate_attempt_records_provider_failure_without_prompt_logging_contract() -> None:
    async def scenario() -> None:
        catalog = build_staging_catalog(openai_enabled=True)
        provider = FakeProvider(
            "openai",
            outcomes=(FailureCategory.RATE_LIMITED,),
        )
        evaluator = CandidateEvaluator(catalog, ProviderRegistry((provider,)))
        attempt = await evaluator.attempt(
            _ref(catalog, "gpt-5-nano"), _routing_request(), _provider_request()
        )
        assert attempt.succeeded is False
        assert attempt.result is None
        assert attempt.failure_category is FailureCategory.RATE_LIMITED

    asyncio.run(scenario())
