"""Deterministic quality-first, sensitivity, health, context, and cost routing matrix."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.ai_router.catalog import DEFAULT_MODEL_CATALOG, ModelCatalog
from backend.app.ai_router.enums import (
    Complexity,
    ModelClass,
    ProviderHealth,
    RoutingOutcome,
    RoutingReason,
)
from backend.app.ai_router.policy import AIRoutingPolicy, CostBudgetPolicy, CostUsageSnapshot
from backend.app.ai_router.schemas import ProviderHealthSnapshot, RoutingRequest
from backend.app.security.classification import DataSensitivity
from tests.phase5_helpers import routing_catalog


def request(
    complexity: Complexity = Complexity.MEDIUM,
    *,
    sensitivity: DataSensitivity = DataSensitivity.PUBLIC,
    context_sensitivities: tuple[DataSensitivity, ...] = (),
    input_tokens: int = 100,
    output_tokens: int = 100,
    realtime_required: bool = False,
    embedding_required: bool = False,
    structured_output_required: bool = False,
    tool_calling_required: bool = False,
    local_only: bool = False,
) -> RoutingRequest:
    return RoutingRequest(
        task_type="assistant.response",
        complexity=complexity,
        sensitivity=sensitivity,
        context_sensitivities=context_sensitivities,
        estimated_input_tokens=input_tokens,
        requested_output_tokens=output_tokens,
        realtime_required=realtime_required,
        embedding_required=embedding_required,
        structured_output_required=structured_output_required,
        tool_calling_required=tool_calling_required,
        local_only=local_only,
    )


@pytest.mark.parametrize(
    ("complexity", "expected_class"),
    [
        (Complexity.TRIVIAL, ModelClass.FAST),
        (Complexity.LOW, ModelClass.FAST),
        (Complexity.MEDIUM, ModelClass.STANDARD),
        (Complexity.HIGH, ModelClass.ADVANCED),
        (Complexity.VERY_HIGH, ModelClass.ADVANCED),
    ],
)
def test_complexity_selects_smallest_sufficient_quality_class(
    complexity: Complexity,
    expected_class: ModelClass,
) -> None:
    decision = AIRoutingPolicy(routing_catalog()).decide(uuid4(), request(complexity))
    assert decision.outcome is RoutingOutcome.SELECTED
    assert decision.selected_model is not None
    assert decision.selected_model.model_class is expected_class


def test_required_capability_escalates_quality_without_weak_emulation() -> None:
    decision = AIRoutingPolicy(routing_catalog()).decide(
        uuid4(), request(Complexity.LOW, tool_calling_required=True)
    )
    assert decision.selected_model is not None
    assert decision.selected_model.model_class is ModelClass.STANDARD
    assert RoutingReason.REQUIRED_CAPABILITY in decision.reason_codes
    assert RoutingReason.QUALITY_ESCALATION in decision.reason_codes


def test_structured_realtime_embedding_and_local_require_declared_capability() -> None:
    policy = AIRoutingPolicy(routing_catalog())
    structured = policy.decide(uuid4(), request(Complexity.LOW, structured_output_required=True))
    realtime = policy.decide(uuid4(), request(realtime_required=True))
    embedding = policy.decide(
        uuid4(), request(Complexity.LOW, embedding_required=True, output_tokens=1)
    )
    local = policy.decide(
        uuid4(),
        request(
            Complexity.HIGH,
            sensitivity=DataSensitivity.CRITICAL,
            local_only=True,
        ),
    )
    assert structured.selected_model and structured.selected_model.model_class is ModelClass.FAST
    assert realtime.selected_model and realtime.selected_model.model_class is ModelClass.REALTIME
    assert embedding.selected_model and embedding.selected_model.model_class is ModelClass.EMBEDDING
    assert local.selected_model and local.selected_model.model_class is ModelClass.LOCAL


def test_context_and_output_limits_escalate_or_deny_without_truncation() -> None:
    policy = AIRoutingPolicy(routing_catalog())
    context_escalation = policy.decide(
        uuid4(), request(Complexity.LOW, input_tokens=8_000, output_tokens=1_000)
    )
    output_escalation = policy.decide(
        uuid4(), request(Complexity.LOW, input_tokens=100, output_tokens=3_000)
    )
    no_context = policy.decide(
        uuid4(), request(Complexity.HIGH, input_tokens=150_000, output_tokens=100)
    )
    no_output = policy.decide(
        uuid4(), request(Complexity.HIGH, input_tokens=100, output_tokens=40_000)
    )
    assert context_escalation.selected_model
    assert context_escalation.selected_model.model_class is ModelClass.STANDARD
    assert output_escalation.selected_model
    assert output_escalation.selected_model.model_class is ModelClass.STANDARD
    assert no_context.outcome is RoutingOutcome.DENIED
    assert no_context.reason_codes == (RoutingReason.CONTEXT_LIMIT,)
    assert no_output.reason_codes == (RoutingReason.OUTPUT_LIMIT,)


@pytest.mark.parametrize(
    "sensitivity",
    [DataSensitivity.PUBLIC, DataSensitivity.INTERNAL, DataSensitivity.PRIVATE],
)
def test_public_internal_and_private_data_route_only_to_approved_models(
    sensitivity: DataSensitivity,
) -> None:
    decision = AIRoutingPolicy(routing_catalog()).decide(
        uuid4(), request(Complexity.MEDIUM, sensitivity=sensitivity)
    )
    assert decision.outcome is RoutingOutcome.SELECTED
    assert decision.selected_model is not None
    assert decision.selected_model.provider_key in {"primary", "equivalent"}


def test_sensitive_uses_explicitly_approved_provider_and_critical_fails_closed() -> None:
    policy = AIRoutingPolicy(routing_catalog())
    sensitive = policy.decide(
        uuid4(), request(Complexity.MEDIUM, sensitivity=DataSensitivity.SENSITIVE)
    )
    critical_external = policy.decide(
        uuid4(), request(Complexity.MEDIUM, sensitivity=DataSensitivity.CRITICAL)
    )
    assert sensitive.selected_model is not None
    assert sensitive.selected_model.provider_key == "sensitive-approved"
    assert critical_external.outcome is RoutingOutcome.DENIED
    assert critical_external.reason_codes == (RoutingReason.SENSITIVITY_RESTRICTION,)


def test_memory_context_labels_cannot_be_downgraded_by_request_sensitivity() -> None:
    routing_request = request(
        Complexity.MEDIUM,
        sensitivity=DataSensitivity.PUBLIC,
        context_sensitivities=(DataSensitivity.CRITICAL,),
    )
    decision = AIRoutingPolicy(routing_catalog()).decide(uuid4(), routing_request)
    assert routing_request.effective_sensitivity is DataSensitivity.CRITICAL
    assert decision.outcome is RoutingOutcome.DENIED
    assert decision.reason_codes == (RoutingReason.SENSITIVITY_RESTRICTION,)


def test_provider_health_is_trusted_policy_input_and_never_request_input() -> None:
    policy = AIRoutingPolicy(routing_catalog())
    unavailable = ProviderHealthSnapshot({"primary": ProviderHealth.UNAVAILABLE})
    decision = policy.decide(uuid4(), request(Complexity.LOW), unavailable)
    assert decision.selected_model is not None
    assert decision.selected_model.provider_key == "equivalent"

    degraded = ProviderHealthSnapshot({"primary": ProviderHealth.DEGRADED})
    degraded_decision = policy.decide(uuid4(), request(Complexity.LOW), degraded)
    assert degraded_decision.selected_model is not None
    assert degraded_decision.selected_model.provider_key == "equivalent"

    disabled = ProviderHealthSnapshot(
        {
            "primary": ProviderHealth.DISABLED,
            "equivalent": ProviderHealth.DISABLED,
            "sensitive-approved": ProviderHealth.DISABLED,
            "local-approved": ProviderHealth.DISABLED,
        }
    )
    denied = policy.decide(uuid4(), request(Complexity.LOW), disabled)
    assert denied.reason_codes == (RoutingReason.PROVIDER_UNAVAILABLE,)
    with pytest.raises(ValidationError):
        RoutingRequest.model_validate(
            {
                "task_type": "assistant.response",
                "complexity": "LOW",
                "sensitivity": "PUBLIC",
                "estimated_input_tokens": 1,
                "requested_output_tokens": 1,
                "provider_health": {"primary": "AVAILABLE"},
            }
        )


def test_cost_optimizes_only_between_equivalent_quality_and_never_weakens_quality() -> None:
    policy = AIRoutingPolicy(routing_catalog())
    cheap_equivalent = policy.decide(uuid4(), request(Complexity.LOW))
    advanced = policy.decide(uuid4(), request(Complexity.HIGH))
    assert cheap_equivalent.selected_model is not None
    assert cheap_equivalent.selected_model.provider_key == "primary"
    assert RoutingReason.COST_NEUTRAL_OPTIMIZATION in cheap_equivalent.reason_codes
    assert advanced.selected_model is not None
    assert advanced.selected_model.model_class is ModelClass.ADVANCED


def test_soft_budget_warns_and_hard_budget_denies_without_quality_degradation() -> None:
    catalog = routing_catalog()
    soft = AIRoutingPolicy(catalog, budget=CostBudgetPolicy(soft_request_microunits=1))
    hard = AIRoutingPolicy(catalog, budget=CostBudgetPolicy(hard_request_microunits=1))
    warned = soft.decide(uuid4(), request(Complexity.HIGH))
    denied = hard.decide(uuid4(), request(Complexity.HIGH))
    assert warned.selected_model is not None
    assert warned.selected_model.model_class is ModelClass.ADVANCED
    assert RoutingReason.BUDGET_WARNING in warned.reason_codes
    assert denied.outcome is RoutingOutcome.DENIED
    assert denied.reason_codes == (RoutingReason.HARD_BUDGET_EXCEEDED,)


def test_daily_and_monthly_budgets_use_trusted_aggregate_snapshot() -> None:
    catalog = routing_catalog()
    policy = AIRoutingPolicy(
        catalog,
        budget=CostBudgetPolicy(
            daily_soft_microunits=100,
            monthly_hard_microunits=1_000,
        ),
    )
    warning = policy.decide(
        uuid4(),
        request(Complexity.MEDIUM),
        usage=CostUsageSnapshot(daily_microunits=99, monthly_microunits=100),
    )
    denial = policy.decide(
        uuid4(),
        request(Complexity.MEDIUM),
        usage=CostUsageSnapshot(daily_microunits=0, monthly_microunits=999),
    )
    assert warning.selected_model is not None
    assert RoutingReason.BUDGET_WARNING in warning.reason_codes
    assert denial.outcome is RoutingOutcome.DENIED
    assert denial.reason_codes == (RoutingReason.HARD_BUDGET_EXCEEDED,)


def test_deprecated_model_is_never_selected_when_an_eligible_peer_exists() -> None:
    base = routing_catalog()
    models = tuple(
        item.model_copy(update={"deprecated": True}) if item.model_id == "advanced" else item
        for item in base.models
    )
    decision = AIRoutingPolicy(ModelCatalog(base.providers, models)).decide(
        uuid4(), request(Complexity.HIGH)
    )
    assert decision.selected_model is not None
    assert decision.selected_model.model_id == "advanced-equivalent"


def test_default_disabled_catalog_fails_closed_without_credentials() -> None:
    decision = AIRoutingPolicy(DEFAULT_MODEL_CATALOG).decide(uuid4(), request())
    assert decision.outcome is RoutingOutcome.DENIED
    assert decision.reason_codes == (RoutingReason.PROVIDER_UNAVAILABLE,)


def test_same_inputs_produce_same_semantic_decision_and_fallback_chain() -> None:
    user_id = uuid4()
    policy = AIRoutingPolicy(routing_catalog())
    first = policy.decide(user_id, request(Complexity.MEDIUM))
    second = policy.decide(user_id, request(Complexity.MEDIUM))
    assert first.selected_model == second.selected_model
    assert first.reason_codes == second.reason_codes
    assert first.fallback_chain == second.fallback_chain
    assert first.estimated_cost_microunits == second.estimated_cost_microunits


def test_request_has_no_model_provider_sensitivity_or_quality_bypass_fields() -> None:
    payload = {
        "task_type": "assistant.response",
        "complexity": "LOW",
        "sensitivity": "PUBLIC",
        "estimated_input_tokens": 1,
        "requested_output_tokens": 1,
    }
    for field, value in (
        ("force_model", "hidden-model"),
        ("force_provider", "disabled"),
        ("ignore_sensitivity", True),
        ("disable_quality_gate", True),
        ("skip_router", True),
    ):
        with pytest.raises(ValidationError):
            RoutingRequest.model_validate({**payload, field: value})
