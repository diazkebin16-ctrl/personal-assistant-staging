"""Central deterministic quality, sensitivity, health, and cost routing policy."""

from dataclasses import dataclass
from uuid import UUID

from backend.app.ai_router.catalog import ModelCatalog
from backend.app.ai_router.enums import (
    Complexity,
    ModelCapability,
    ModelClass,
    ProviderHealth,
    QualityTier,
    RoutingOutcome,
    RoutingReason,
)
from backend.app.ai_router.schemas import (
    ModelDefinition,
    ModelReference,
    ProviderDefinition,
    ProviderHealthSnapshot,
    RoutingDecision,
    RoutingRequest,
)
from backend.app.security.classification import DataSensitivity, sensitivity_rank

POLICY_VERSION = "ai-router-v1"

_GENERAL_MODEL_RANK = {
    ModelClass.FAST: 1,
    ModelClass.STANDARD: 2,
    ModelClass.ADVANCED: 3,
}


@dataclass(frozen=True, slots=True)
class CostBudgetPolicy:
    """Server-owned request budget; soft thresholds observe, hard limits deny."""

    soft_request_microunits: int | None = None
    hard_request_microunits: int | None = None
    daily_soft_microunits: int | None = None
    monthly_soft_microunits: int | None = None
    daily_hard_microunits: int | None = None
    monthly_hard_microunits: int | None = None

    def __post_init__(self) -> None:
        for value in (
            self.soft_request_microunits,
            self.hard_request_microunits,
            self.daily_soft_microunits,
            self.monthly_soft_microunits,
            self.daily_hard_microunits,
            self.monthly_hard_microunits,
        ):
            if value is not None and value < 0:
                raise ValueError("Cost budget values cannot be negative")
        if (
            self.soft_request_microunits is not None
            and self.hard_request_microunits is not None
            and self.soft_request_microunits > self.hard_request_microunits
        ):
            raise ValueError("Soft request budget cannot exceed the hard request budget")


@dataclass(frozen=True, slots=True)
class CostUsageSnapshot:
    """Trusted aggregate usage input; callers cannot place it in RoutingRequest."""

    daily_microunits: int = 0
    monthly_microunits: int = 0

    def __post_init__(self) -> None:
        if self.daily_microunits < 0 or self.monthly_microunits < 0:
            raise ValueError("Aggregate cost usage cannot be negative")


class SensitivityRoutingPolicy:
    """Conservative provider/model data eligibility with explicit approvals."""

    @staticmethod
    def allows(
        sensitivity: DataSensitivity,
        provider: ProviderDefinition,
        model: ModelDefinition,
    ) -> bool:
        if sensitivity_rank(sensitivity) > sensitivity_rank(provider.max_sensitivity):
            return False
        if sensitivity_rank(sensitivity) > sensitivity_rank(model.max_sensitivity):
            return False
        if sensitivity is DataSensitivity.PRIVATE and not provider.private_data_approved:
            return False
        if sensitivity is DataSensitivity.SENSITIVE and not provider.sensitive_data_approved:
            return False
        if sensitivity is DataSensitivity.CRITICAL:
            return provider.local and provider.critical_data_approved
        return True


class AIRoutingPolicy:
    """Pure policy: the same inputs and catalog produce the same selected model."""

    def __init__(
        self,
        catalog: ModelCatalog,
        *,
        budget: CostBudgetPolicy | None = None,
        sensitivity_policy: SensitivityRoutingPolicy | None = None,
    ) -> None:
        self.catalog = catalog
        self.budget = budget or CostBudgetPolicy()
        self.sensitivity_policy = sensitivity_policy or SensitivityRoutingPolicy()

    def decide(
        self,
        user_id: UUID,
        request: RoutingRequest,
        health: ProviderHealthSnapshot | None = None,
        usage: CostUsageSnapshot | None = None,
    ) -> RoutingDecision:
        snapshot = health or ProviderHealthSnapshot()
        cost_usage = usage or CostUsageSnapshot()
        target_class, base_reason = self._target_class(request)
        required = request.effective_capabilities

        available = [
            model
            for model in self.catalog.models
            if model.enabled
            and not model.deprecated
            and self.catalog.provider(model.provider_key).enabled
            and snapshot.status_for(model.provider_key)
            not in {ProviderHealth.UNAVAILABLE, ProviderHealth.DISABLED}
        ]
        if not available:
            return self._denied(user_id, request, RoutingReason.PROVIDER_UNAVAILABLE)

        class_candidates = [
            model for model in available if self._meets_class(model, target_class, request)
        ]
        if request.local_only:
            class_candidates = [
                model
                for model in class_candidates
                if self.catalog.provider(model.provider_key).local
            ]
        if not class_candidates:
            reason = (
                RoutingReason.LOCAL_ONLY_REQUIRED
                if request.local_only
                else RoutingReason.NO_ELIGIBLE_MODEL
            )
            return self._denied(user_id, request, reason)

        capable = [model for model in class_candidates if required.issubset(model.capabilities)]
        if not capable:
            return self._denied(user_id, request, RoutingReason.REQUIRED_CAPABILITY)

        sensitivity_eligible = [
            model
            for model in capable
            if self.sensitivity_policy.allows(
                request.effective_sensitivity,
                self.catalog.provider(model.provider_key),
                model,
            )
        ]
        if not sensitivity_eligible:
            return self._denied(user_id, request, RoutingReason.SENSITIVITY_RESTRICTION)

        output_eligible = [
            model
            for model in sensitivity_eligible
            if request.requested_output_tokens <= model.output_limit
        ]
        if not output_eligible:
            return self._denied(user_id, request, RoutingReason.OUTPUT_LIMIT)

        total_tokens = request.estimated_input_tokens + request.requested_output_tokens
        context_eligible = [
            model for model in output_eligible if total_tokens <= model.context_limit
        ]
        if not context_eligible:
            return self._denied(user_id, request, RoutingReason.CONTEXT_LIMIT)

        ordered = sorted(
            context_eligible,
            key=lambda model: self._selection_key(model, request, snapshot),
        )
        selected = ordered[0]
        estimated_cost = selected.pricing.estimate_microunits(
            request.estimated_input_tokens,
            request.requested_output_tokens,
        )
        if (
            (
                self.budget.hard_request_microunits is not None
                and estimated_cost > self.budget.hard_request_microunits
            )
            or (
                self.budget.daily_hard_microunits is not None
                and cost_usage.daily_microunits + estimated_cost > self.budget.daily_hard_microunits
            )
            or (
                self.budget.monthly_hard_microunits is not None
                and cost_usage.monthly_microunits + estimated_cost
                > self.budget.monthly_hard_microunits
            )
        ):
            return self._denied(user_id, request, RoutingReason.HARD_BUDGET_EXCEEDED)

        reasons: list[RoutingReason] = [base_reason]
        if required - {self._base_capability(request)}:
            reasons.append(RoutingReason.REQUIRED_CAPABILITY)
        if self._is_quality_escalation(selected, target_class):
            reasons.append(RoutingReason.QUALITY_ESCALATION)
        equivalent = [
            model
            for model in ordered
            if model.model_class is selected.model_class
            and model.quality_tier is selected.quality_tier
        ]
        if len(equivalent) > 1:
            reasons.append(RoutingReason.COST_NEUTRAL_OPTIMIZATION)
        if (
            (
                self.budget.soft_request_microunits is not None
                and estimated_cost > self.budget.soft_request_microunits
            )
            or (
                self.budget.daily_soft_microunits is not None
                and cost_usage.daily_microunits + estimated_cost > self.budget.daily_soft_microunits
            )
            or (
                self.budget.monthly_soft_microunits is not None
                and cost_usage.monthly_microunits + estimated_cost
                > self.budget.monthly_soft_microunits
            )
        ):
            reasons.append(RoutingReason.BUDGET_WARNING)

        fallbacks = self._fallbacks(selected, ordered, snapshot, request)
        if any(
            item.provider_key != selected.provider_key
            and item.model_class is selected.model_class
            and item.quality_tier is selected.quality_tier
            for item in fallbacks
        ):
            reasons.append(RoutingReason.EQUIVALENT_PROVIDER_FALLBACK)
        return RoutingDecision(
            user_id=user_id,
            task_id=request.task_id,
            outcome=RoutingOutcome.SELECTED,
            selected_model=ModelReference.from_definition(selected),
            reason_codes=tuple(dict.fromkeys(reasons)),
            policy_version=POLICY_VERSION,
            required_capabilities=tuple(sorted(required, key=lambda item: item.value)),
            effective_sensitivity=request.effective_sensitivity,
            fallback_chain=fallbacks,
            estimated_cost_microunits=estimated_cost,
        )

    @staticmethod
    def _target_class(request: RoutingRequest) -> tuple[ModelClass, RoutingReason]:
        if request.embedding_required:
            return ModelClass.EMBEDDING, RoutingReason.EMBEDDING_REQUIRED
        if request.realtime_required:
            return ModelClass.REALTIME, RoutingReason.REALTIME_REQUIRED
        if request.local_only:
            return ModelClass.LOCAL, RoutingReason.LOCAL_ONLY_REQUIRED
        if request.complexity in {Complexity.TRIVIAL, Complexity.LOW}:
            return ModelClass.FAST, RoutingReason.LOW_COMPLEXITY_FAST
        if request.complexity is Complexity.MEDIUM:
            return ModelClass.STANDARD, RoutingReason.DEFAULT_STANDARD
        return ModelClass.ADVANCED, RoutingReason.HIGH_COMPLEXITY_ADVANCED

    @staticmethod
    def _base_capability(request: RoutingRequest) -> ModelCapability:
        if request.embedding_required:
            return ModelCapability.EMBEDDINGS
        if request.realtime_required:
            return ModelCapability.AUDIO_REALTIME
        return ModelCapability.TEXT_GENERATION

    @staticmethod
    def _meets_class(
        model: ModelDefinition,
        target_class: ModelClass,
        request: RoutingRequest,
    ) -> bool:
        if target_class in {ModelClass.REALTIME, ModelClass.EMBEDDING}:
            return model.model_class is target_class
        if target_class is ModelClass.LOCAL:
            return (
                model.model_class is ModelClass.LOCAL
                and model.quality_tier >= AIRoutingPolicy._quality_floor(request.complexity)
            )
        if model.model_class not in _GENERAL_MODEL_RANK:
            return False
        required_rank = _GENERAL_MODEL_RANK[target_class]
        model_rank = _GENERAL_MODEL_RANK[model.model_class]
        quality_floor = AIRoutingPolicy._quality_floor(request.complexity)
        return model_rank >= required_rank and model.quality_tier >= quality_floor

    @staticmethod
    def _quality_floor(complexity: Complexity) -> QualityTier:
        return {
            Complexity.TRIVIAL: QualityTier.FAST,
            Complexity.LOW: QualityTier.FAST,
            Complexity.MEDIUM: QualityTier.STANDARD,
            Complexity.HIGH: QualityTier.ADVANCED,
            Complexity.VERY_HIGH: QualityTier.ADVANCED,
        }[complexity]

    def _selection_key(
        self,
        model: ModelDefinition,
        request: RoutingRequest,
        health: ProviderHealthSnapshot,
    ) -> tuple[int, int, int, int, int, int, str, str]:
        model_rank = _GENERAL_MODEL_RANK.get(model.model_class, 4)
        health_rank = 0 if health.status_for(model.provider_key) is ProviderHealth.AVAILABLE else 1
        estimate = model.pricing.estimate_microunits(
            request.estimated_input_tokens,
            request.requested_output_tokens,
        )
        provider_sensitivity_rank = sensitivity_rank(
            self.catalog.provider(model.provider_key).max_sensitivity
        )
        return (
            model_rank,
            int(model.quality_tier),
            health_rank,
            provider_sensitivity_rank,
            estimate,
            model.fallback_priority,
            model.provider_key,
            model.model_id,
        )

    @staticmethod
    def _is_quality_escalation(selected: ModelDefinition, target: ModelClass) -> bool:
        if target not in _GENERAL_MODEL_RANK or selected.model_class not in _GENERAL_MODEL_RANK:
            return False
        return _GENERAL_MODEL_RANK[selected.model_class] > _GENERAL_MODEL_RANK[target]

    def _fallbacks(
        self,
        selected: ModelDefinition,
        ordered: list[ModelDefinition],
        health: ProviderHealthSnapshot,
        request: RoutingRequest,
    ) -> tuple[ModelReference, ...]:
        candidates = [model for model in ordered if model is not selected]
        candidates.sort(
            key=lambda model: (
                0
                if (
                    model.model_class is selected.model_class
                    and model.quality_tier is selected.quality_tier
                )
                else 1,
                *self._selection_key(model, request, health),
            )
        )
        return tuple(ModelReference.from_definition(model) for model in candidates)

    @staticmethod
    def _denied(
        user_id: UUID,
        request: RoutingRequest,
        reason: RoutingReason,
    ) -> RoutingDecision:
        return RoutingDecision(
            user_id=user_id,
            task_id=request.task_id,
            outcome=RoutingOutcome.DENIED,
            selected_model=None,
            reason_codes=(reason,),
            policy_version=POLICY_VERSION,
            required_capabilities=tuple(
                sorted(request.effective_capabilities, key=lambda item: item.value)
            ),
            effective_sensitivity=request.effective_sensitivity,
        )
