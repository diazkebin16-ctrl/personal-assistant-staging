"""Explicit Gemini candidate evaluation without normal-routing eligibility."""

import asyncio

import pytest

from backend.app.ai_router.catalog import build_staging_catalog
from backend.app.ai_router.enums import Complexity
from backend.app.ai_router.evaluation import CandidateEvaluator
from backend.app.ai_router.provider import FakeProvider, ProviderRegistry
from backend.app.ai_router.schemas import (
    ModelReference,
    ProviderRequest,
    ProviderResponse,
    RoutingRequest,
)
from backend.app.core.errors import AIRoutingDeniedError
from backend.app.security.classification import DataSensitivity


def _candidate(catalog: object) -> ModelReference:
    evaluation_models = getattr(catalog, "evaluation_models")
    model = next(item for item in evaluation_models if item.provider_key == "gemini")
    return ModelReference.from_definition(model)


def _routing_request(sensitivity: DataSensitivity) -> RoutingRequest:
    return RoutingRequest(
        task_type="candidate.evaluation",
        complexity=Complexity.LOW,
        sensitivity=sensitivity,
        estimated_input_tokens=6,
        requested_output_tokens=8,
    )


def test_public_candidate_can_be_invoked_explicitly_with_usage_cost_and_latency() -> None:
    async def scenario() -> None:
        catalog = build_staging_catalog(openai_enabled=False, gemini_enabled=True)
        response = ProviderResponse(
            output_text="GEMINI_OK",
            input_tokens=6,
            output_tokens=2,
            cached_tokens=0,
        )
        gemini = FakeProvider("gemini", (response,))
        evaluator = CandidateEvaluator(catalog, ProviderRegistry((gemini,)))

        result = await evaluator.evaluate(
            _candidate(catalog),
            _routing_request(DataSensitivity.PUBLIC),
            ProviderRequest(
                input_text="Reply with exactly: GEMINI_OK",
                output_token_budget=8,
            ),
        )

        assert result.model.provider_key == "gemini"
        assert result.model.model_id == "gemini-2.5-flash-lite"
        assert result.response.output_text == "GEMINI_OK"
        assert result.response.input_tokens == 6
        assert result.response.output_tokens == 2
        assert result.latency_ms >= 0
        assert result.estimated_cost_microunits == 2
        assert gemini.call_count == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "sensitivity",
    [
        DataSensitivity.PRIVATE,
        DataSensitivity.SENSITIVE,
        DataSensitivity.CRITICAL,
    ],
)
def test_non_public_candidate_evaluation_fails_before_provider_invocation(
    sensitivity: DataSensitivity,
) -> None:
    async def scenario() -> None:
        catalog = build_staging_catalog(openai_enabled=False, gemini_enabled=True)
        gemini = FakeProvider(
            "gemini",
            (ProviderResponse(output_text="must not run", input_tokens=1, output_tokens=1),),
        )
        evaluator = CandidateEvaluator(catalog, ProviderRegistry((gemini,)))

        with pytest.raises(AIRoutingDeniedError):
            await evaluator.evaluate(
                _candidate(catalog),
                _routing_request(sensitivity),
                ProviderRequest(input_text="not sent", output_token_budget=8),
            )
        assert gemini.call_count == 0

    asyncio.run(scenario())


def test_candidate_cannot_expand_capabilities_or_output_budget() -> None:
    async def scenario() -> None:
        catalog = build_staging_catalog(openai_enabled=False, gemini_enabled=True)
        gemini = FakeProvider(
            "gemini",
            (ProviderResponse(output_text="must not run", input_tokens=1, output_tokens=1),),
        )
        evaluator = CandidateEvaluator(catalog, ProviderRegistry((gemini,)))

        with pytest.raises(AIRoutingDeniedError):
            await evaluator.evaluate(
                _candidate(catalog),
                _routing_request(DataSensitivity.PUBLIC),
                ProviderRequest(
                    input_text="public",
                    output_token_budget=9,
                ),
            )
        assert gemini.call_count == 0

    asyncio.run(scenario())
