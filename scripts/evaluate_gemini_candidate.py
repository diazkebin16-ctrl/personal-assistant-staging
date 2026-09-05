"""Run one minimal PUBLIC Gemini candidate connectivity evaluation."""

import asyncio

from backend.app.ai_router.composition import build_configured_ai_components
from backend.app.ai_router.enums import Complexity
from backend.app.ai_router.evaluation import CandidateEvaluator
from backend.app.ai_router.schemas import ModelReference, ProviderRequest, RoutingRequest
from backend.app.core.config import get_settings
from backend.app.security.classification import DataSensitivity

_MODEL_ID = "gemini-2.5-flash-lite"
_EXPECTED = "GEMINI_OK"


async def main() -> int:
    settings = get_settings()
    catalog, providers = build_configured_ai_components(settings)
    candidate = next(
        (
            model
            for model in catalog.evaluation_models
            if model.provider_key == "gemini" and model.model_id == _MODEL_ID
        ),
        None,
    )
    if candidate is None or not candidate.enabled:
        print(f"model={_MODEL_ID} status=not_configured")
        return 2

    evaluator = CandidateEvaluator(catalog, providers)
    result = await evaluator.evaluate(
        ModelReference.from_definition(candidate),
        RoutingRequest(
            task_type="candidate.connectivity",
            complexity=Complexity.LOW,
            sensitivity=DataSensitivity.PUBLIC,
            estimated_input_tokens=8,
            requested_output_tokens=16,
        ),
        ProviderRequest(
            input_text="Reply with exactly: GEMINI_OK",
            output_token_budget=16,
        ),
    )

    if result.response.output_text.strip() != _EXPECTED:
        print(
            f"model={_MODEL_ID} status=unexpected_response "
            f"latency_ms={result.latency_ms} input_tokens={result.response.input_tokens} "
            f"output_tokens={result.response.output_tokens} "
            f"cached_tokens={result.response.cached_tokens}"
        )
        return 3

    print(
        f"model={_MODEL_ID} status=ok latency_ms={result.latency_ms} "
        f"input_tokens={result.response.input_tokens} "
        f"output_tokens={result.response.output_tokens} "
        f"cached_tokens={result.response.cached_tokens} "
        f"estimated_cost_microunits={result.estimated_cost_microunits}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
