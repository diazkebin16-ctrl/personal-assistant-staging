"""GPT-5 Nano candidate catalog, routing, privacy, and dependency invariants."""

from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.ai_router.benchmark import NANO_LUNA_BENCHMARK_CASES
from backend.app.ai_router.catalog import build_staging_catalog
from backend.app.ai_router.composition import build_configured_ai_components
from backend.app.ai_router.enums import Complexity, FailureCategory, ModelClass, RoutingOutcome
from backend.app.ai_router.policy import AIRoutingPolicy, SensitivityRoutingPolicy
from backend.app.ai_router.provider import ProviderFailure
from backend.app.ai_router.schemas import ModelReference, RoutingRequest
from backend.app.core.config import Settings
from backend.app.security.classification import DataSensitivity


def _request(complexity: Complexity = Complexity.LOW, sensitivity: DataSensitivity = DataSensitivity.PUBLIC) -> RoutingRequest:
    return RoutingRequest(
        task_type="assistant.response",
        complexity=complexity,
        sensitivity=sensitivity,
        estimated_input_tokens=20,
        requested_output_tokens=20,
    )


def _model_ref(model_id: str) -> ModelReference:
    catalog = build_staging_catalog(openai_enabled=True)
    model = next(item for item in catalog.all_models if item.model_id == model_id)
    return ModelReference.from_definition(model)


def test_gemini_is_absent_and_nano_is_evaluation_only() -> None:
    catalog = build_staging_catalog(openai_enabled=True)
    ids = {model.model_id for model in catalog.all_models}
    provider_keys = {provider.key for provider in catalog.providers}
    nano = catalog.model(_model_ref("gpt-5-nano"))
    assert all("gemini" not in value for value in ids | provider_keys)
    assert nano.enabled is True
    assert nano.routing_enabled is False
    assert nano.evaluation_enabled is True
    assert nano not in catalog.models
    assert nano in catalog.evaluation_models


def test_normal_routing_stays_luna_terra_sol_and_never_nano() -> None:
    catalog = build_staging_catalog(openai_enabled=True)
    policy = AIRoutingPolicy(catalog)
    expected = {
        Complexity.LOW: "gpt-5.6-luna",
        Complexity.MEDIUM: "gpt-5.6-terra",
        Complexity.HIGH: "gpt-5.6-sol",
    }
    for complexity, model_id in expected.items():
        decision = policy.decide(uuid4(), _request(complexity))
        assert decision.outcome is RoutingOutcome.SELECTED
        assert decision.selected_model is not None
        assert decision.selected_model.model_id == model_id
        assert all(item.model_id != "gpt-5-nano" for item in decision.fallback_chain)


def test_nano_official_catalog_limits_pricing_and_openai_privacy_boundary() -> None:
    catalog = build_staging_catalog(openai_enabled=True)
    nano = catalog.model(_model_ref("gpt-5-nano"))
    provider = catalog.provider("openai")
    assert nano.model_class is ModelClass.FAST
    assert nano.context_limit == 400_000
    assert nano.output_limit == 128_000
    assert nano.pricing.input_microunits_per_million_tokens == 50_000
    assert nano.pricing.cached_input_microunits_per_million_tokens == 5_000
    assert nano.pricing.output_microunits_per_million_tokens == 400_000
    assert provider.max_sensitivity is DataSensitivity.PRIVATE
    assert provider.private_data_approved is True
    assert SensitivityRoutingPolicy.allows(DataSensitivity.PRIVATE, provider, nano) is True
    assert SensitivityRoutingPolicy.allows(DataSensitivity.SENSITIVE, provider, nano) is False
    assert SensitivityRoutingPolicy.allows(DataSensitivity.CRITICAL, provider, nano) is False


def test_composition_registers_only_openai_and_no_gemini_registry() -> None:
    catalog, providers = build_configured_ai_components(
        Settings.model_validate({"OPENAI_API_KEY": "openai-test-only"})
    )
    assert {provider.key for provider in catalog.providers} == {"openai"}
    assert providers.get("openai").key == "openai"
    with pytest.raises(ProviderFailure) as failure:
        providers.get("gemini")
    assert failure.value.category is FailureCategory.PROVIDER_UNAVAILABLE


def test_no_credentials_remains_fail_closed() -> None:
    catalog, providers = build_configured_ai_components(Settings.model_validate({}))
    decision = AIRoutingPolicy(catalog).decide(uuid4(), _request())
    assert decision.outcome is RoutingOutcome.DENIED
    with pytest.raises(ProviderFailure):
        providers.get("openai")


def test_google_genai_is_not_a_project_dependency() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8").casefold()
    lock = Path("uv.lock").read_text(encoding="utf-8").casefold()
    assert "google-genai" not in pyproject
    assert "google-genai" not in lock
    assert "gemini_api_key" not in Path("backend/app/core/config.py").read_text(encoding="utf-8")


def test_benchmark_is_offline_and_contains_ten_representative_cases() -> None:
    assert len(NANO_LUNA_BENCHMARK_CASES) == 10
    keys = {case.key for case in NANO_LUNA_BENCHMARK_CASES}
    assert {"greeting", "simple_fact", "recent_follow_up", "allowed_context"} <= keys
    boundary = next(case for case in NANO_LUNA_BENCHMARK_CASES if case.requires_stronger_reasoning)
    assert boundary.complexity is Complexity.HIGH
    assert boundary.key == "strong_reasoning_boundary"
