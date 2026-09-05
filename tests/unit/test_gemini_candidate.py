"""Gemini candidate-mode catalog, composition, and routing invariants."""

from uuid import uuid4

import pytest

from backend.app.ai_router.catalog import build_staging_catalog
from backend.app.ai_router.composition import build_configured_ai_components
from backend.app.ai_router.enums import Complexity, FailureCategory, RoutingOutcome
from backend.app.ai_router.policy import AIRoutingPolicy, SensitivityRoutingPolicy
from backend.app.ai_router.provider import ProviderFailure
from backend.app.ai_router.schemas import ModelReference, RoutingRequest
from backend.app.core.config import Settings
from backend.app.security.classification import DataSensitivity


def _request(sensitivity: DataSensitivity = DataSensitivity.PUBLIC) -> RoutingRequest:
    return RoutingRequest(
        task_type="assistant.response",
        complexity=Complexity.LOW,
        sensitivity=sensitivity,
        estimated_input_tokens=20,
        requested_output_tokens=20,
    )


def _gemini_reference() -> ModelReference:
    catalog = build_staging_catalog(openai_enabled=True, gemini_enabled=True)
    candidate = next(
        model for model in catalog.all_models if model.model_id == "gemini-2.5-flash-lite"
    )
    return ModelReference.from_definition(candidate)


def test_gemini_is_explicit_evaluation_only_and_never_normal_routing() -> None:
    catalog = build_staging_catalog(openai_enabled=True, gemini_enabled=True)
    candidate = catalog.model(_gemini_reference())
    decision = AIRoutingPolicy(catalog).decide(uuid4(), _request())

    assert candidate.enabled is True
    assert candidate.routing_enabled is False
    assert candidate.evaluation_enabled is True
    assert candidate not in catalog.models
    assert candidate in catalog.evaluation_models
    assert decision.outcome is RoutingOutcome.SELECTED
    assert decision.selected_model is not None
    assert decision.selected_model.provider_key == "openai"
    assert decision.selected_model.model_id == "gpt-5.6-luna"
    assert all(item.provider_key != "gemini" for item in decision.fallback_chain)


@pytest.mark.parametrize(
    "sensitivity",
    [
        DataSensitivity.PRIVATE,
        DataSensitivity.SENSITIVE,
        DataSensitivity.CRITICAL,
    ],
)
def test_gemini_has_no_private_sensitive_or_critical_approval(
    sensitivity: DataSensitivity,
) -> None:
    catalog = build_staging_catalog(openai_enabled=True, gemini_enabled=True)
    candidate = catalog.model(_gemini_reference())
    provider = catalog.provider("gemini")

    assert provider.max_sensitivity is DataSensitivity.PUBLIC
    assert provider.private_data_approved is False
    assert provider.sensitive_data_approved is False
    assert provider.critical_data_approved is False
    assert SensitivityRoutingPolicy.allows(sensitivity, provider, candidate) is False


def test_openai_without_gemini_remains_configured() -> None:
    catalog, providers = build_configured_ai_components(
        Settings.model_validate({"OPENAI_API_KEY": "openai-test-only"})
    )
    assert catalog.provider("openai").enabled is True
    assert catalog.provider("gemini").enabled is False
    assert providers.get("openai").key == "openai"
    with pytest.raises(ProviderFailure) as failure:
        providers.get("gemini")
    assert failure.value.category is FailureCategory.PROVIDER_UNAVAILABLE


def test_gemini_without_openai_registers_only_as_candidate() -> None:
    catalog, providers = build_configured_ai_components(
        Settings.model_validate({"GEMINI_API_KEY": "gemini-test-only"})
    )
    assert catalog.provider("openai").enabled is False
    assert catalog.provider("gemini").enabled is True
    assert providers.get("gemini").key == "gemini"
    decision = AIRoutingPolicy(catalog).decide(uuid4(), _request())
    assert decision.outcome is RoutingOutcome.DENIED
    with pytest.raises(ProviderFailure) as failure:
        providers.get("openai")
    assert failure.value.category is FailureCategory.PROVIDER_UNAVAILABLE


def test_no_external_credentials_preserves_fail_closed_behavior() -> None:
    catalog, providers = build_configured_ai_components(Settings.model_validate({}))
    decision = AIRoutingPolicy(catalog).decide(uuid4(), _request())
    assert decision.outcome is RoutingOutcome.DENIED
    for provider_key in ("openai", "gemini"):
        with pytest.raises(ProviderFailure):
            providers.get(provider_key)
