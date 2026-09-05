"""Incomplete evaluation accounting through the provider-neutral diagnostic contract."""

import asyncio

from backend.app.ai_router.catalog import ModelCatalog, build_staging_catalog
from backend.app.ai_router.diagnostics import ProviderDiagnosticResponse, ProviderResponseStatus
from backend.app.ai_router.enums import Complexity, ModelCapability
from backend.app.ai_router.evaluation import CandidateEvaluator
from backend.app.ai_router.provider import ProviderRegistry
from backend.app.ai_router.schemas import (
    ModelReference,
    ProviderRequest,
    ProviderResponse,
    RoutingRequest,
)
from backend.app.security.classification import DataSensitivity


class IncompleteDiagnosticProvider:
    key = "openai"

    def __init__(self) -> None:
        self.call_count = 0

    async def generate(self, model_id: str, request: ProviderRequest) -> ProviderResponse:
        raise AssertionError("Explicit evaluation should use diagnostic generation")

    async def generate_for_evaluation(
        self,
        model_id: str,
        request: ProviderRequest,
    ) -> ProviderDiagnosticResponse:
        self.call_count += 1
        return ProviderDiagnosticResponse(
            status=ProviderResponseStatus.INCOMPLETE,
            input_tokens=100,
            cached_tokens=40,
            output_tokens=128,
            reasoning_tokens=128,
            incomplete_reason="max_output_tokens",
            reported_model_id=model_id,
        )


def _ref(catalog: ModelCatalog, model_id: str) -> ModelReference:
    model = next(item for item in catalog.all_models if item.model_id == model_id)
    return ModelReference.from_definition(model)


def test_incomplete_candidate_keeps_usage_latency_and_estimated_cost() -> None:
    async def scenario() -> None:
        catalog = build_staging_catalog(openai_enabled=True)
        provider = IncompleteDiagnosticProvider()
        evaluator = CandidateEvaluator(catalog, ProviderRegistry((provider,)))
        routing_request = RoutingRequest(
            task_type="benchmark.nano_luna",
            complexity=Complexity.TRIVIAL,
            required_capabilities=frozenset({ModelCapability.TEXT_GENERATION}),
            sensitivity=DataSensitivity.PUBLIC,
            estimated_input_tokens=100,
            requested_output_tokens=256,
        )
        provider_request = ProviderRequest(input_text="public fixture", output_token_budget=256)
        result = await evaluator.evaluate(
            _ref(catalog, "gpt-5-nano"), routing_request, provider_request
        )
        assert result.response.status is ProviderResponseStatus.INCOMPLETE
        assert result.response.input_tokens == 100
        assert result.response.cached_tokens == 40
        assert result.response.output_tokens == 128
        assert result.response.reasoning_tokens == 128
        assert result.response.incomplete_reason == "max_output_tokens"
        assert result.latency_ms >= 0
        assert result.estimated_cost_microunits == 55
        assert provider.call_count == 1

    asyncio.run(scenario())
