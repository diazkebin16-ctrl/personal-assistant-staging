"""Internal explicit evaluation path for candidate and routed-baseline models."""

from dataclasses import dataclass
from time import perf_counter

from backend.app.ai_router.catalog import ModelCatalog
from backend.app.ai_router.enums import FailureCategory
from backend.app.ai_router.policy import SensitivityRoutingPolicy
from backend.app.ai_router.provider import ProviderFailure, ProviderRegistry
from backend.app.ai_router.schemas import (
    ModelDefinition,
    ModelReference,
    ProviderRequest,
    ProviderResponse,
    RoutingRequest,
)
from backend.app.core.errors import AIRoutingDeniedError


@dataclass(frozen=True, slots=True)
class CandidateEvaluationResult:
    """Ephemeral evaluation evidence; it contains no credentials or raw request logging."""

    model: ModelReference
    response: ProviderResponse
    latency_ms: int
    estimated_cost_microunits: int


@dataclass(frozen=True, slots=True)
class CandidateEvaluationAttempt:
    """Provider outcome for benchmark aggregation without retaining the private prompt."""

    model: ModelReference
    succeeded: bool
    result: CandidateEvaluationResult | None = None
    failure_category: FailureCategory | None = None


class CandidateEvaluator:
    """Explicit-only evaluator that reuses catalog, privacy policy, and provider adapters."""

    def __init__(
        self,
        catalog: ModelCatalog,
        providers: ProviderRegistry,
        *,
        sensitivity_policy: SensitivityRoutingPolicy | None = None,
    ) -> None:
        self.catalog = catalog
        self.providers = providers
        self.sensitivity_policy = sensitivity_policy or SensitivityRoutingPolicy()

    async def evaluate(
        self,
        model_ref: ModelReference,
        routing_request: RoutingRequest,
        provider_request: ProviderRequest,
    ) -> CandidateEvaluationResult:
        """Evaluate only a model explicitly marked as an evaluation candidate."""
        model = self.catalog.model(model_ref)
        if not model.evaluation_enabled:
            raise AIRoutingDeniedError
        return await self._evaluate(model, model_ref, routing_request, provider_request)

    async def evaluate_routing_baseline(
        self,
        model_ref: ModelReference,
        routing_request: RoutingRequest,
        provider_request: ProviderRequest,
    ) -> CandidateEvaluationResult:
        """Evaluate an already-routable baseline without changing candidate eligibility."""
        model = self.catalog.model(model_ref)
        if not model.routing_enabled:
            raise AIRoutingDeniedError
        return await self._evaluate(model, model_ref, routing_request, provider_request)

    async def attempt(
        self,
        model_ref: ModelReference,
        routing_request: RoutingRequest,
        provider_request: ProviderRequest,
        *,
        routing_baseline: bool = False,
    ) -> CandidateEvaluationAttempt:
        """Record provider success/failure while allowing policy denials to remain fail-closed."""
        try:
            if routing_baseline:
                result = await self.evaluate_routing_baseline(
                    model_ref, routing_request, provider_request
                )
            else:
                result = await self.evaluate(model_ref, routing_request, provider_request)
        except ProviderFailure as exc:
            return CandidateEvaluationAttempt(
                model=model_ref,
                succeeded=False,
                failure_category=exc.category,
            )
        return CandidateEvaluationAttempt(model=model_ref, succeeded=True, result=result)

    async def _evaluate(
        self,
        model: ModelDefinition,
        model_ref: ModelReference,
        routing_request: RoutingRequest,
        provider_request: ProviderRequest,
    ) -> CandidateEvaluationResult:
        provider_definition = self.catalog.provider(model.provider_key)

        if model_ref != ModelReference.from_definition(model):
            raise AIRoutingDeniedError
        if not provider_definition.enabled or not model.enabled or model.deprecated:
            raise AIRoutingDeniedError
        if (
            provider_request.output_token_budget > routing_request.requested_output_tokens
            or (
                provider_request.structured_output_required
                and not routing_request.structured_output_required
            )
            or (
                provider_request.tool_calling_required and not routing_request.tool_calling_required
            )
        ):
            raise AIRoutingDeniedError
        if not routing_request.effective_capabilities.issubset(model.capabilities):
            raise AIRoutingDeniedError
        if not self.sensitivity_policy.allows(
            routing_request.effective_sensitivity,
            provider_definition,
            model,
        ):
            raise AIRoutingDeniedError
        if routing_request.requested_output_tokens > model.output_limit:
            raise AIRoutingDeniedError
        total_tokens = (
            routing_request.estimated_input_tokens + routing_request.requested_output_tokens
        )
        if total_tokens > model.context_limit:
            raise AIRoutingDeniedError

        provider = self.providers.get(model.provider_key)
        started = perf_counter()
        response = await provider.generate(model.model_id, provider_request)
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        if response.output_tokens > provider_request.output_token_budget:
            raise ProviderFailure(FailureCategory.MALFORMED_RESPONSE)

        estimated_cost = model.pricing.estimate_microunits(
            response.input_tokens,
            response.output_tokens,
            cached_tokens=response.cached_tokens,
        )
        return CandidateEvaluationResult(
            model=model_ref,
            response=response,
            latency_ms=latency_ms,
            estimated_cost_microunits=estimated_cost,
        )
