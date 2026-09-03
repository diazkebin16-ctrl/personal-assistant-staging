"""Server-owned model catalog and provider abstraction invariants."""

import asyncio
from datetime import date

import pytest
from pydantic import ValidationError

from backend.app.ai_router.catalog import DEFAULT_MODEL_CATALOG, ModelCatalog
from backend.app.ai_router.enums import (
    FailureCategory,
    LatencyTier,
    ModelCapability,
    ModelClass,
    QualityTier,
    is_retryable_failure,
)
from backend.app.ai_router.provider import FakeProvider, ProviderFailure, ProviderRegistry
from backend.app.ai_router.schemas import (
    ModelDefinition,
    ModelReference,
    PricingMetadata,
    ProviderDefinition,
    ProviderRequest,
    ProviderResponse,
)
from backend.app.security.classification import DataSensitivity
from tests.phase5_helpers import model, pricing, routing_catalog


def test_default_catalog_represents_all_canonical_model_classes_but_enables_nothing() -> None:
    assert {item.model_class for item in DEFAULT_MODEL_CATALOG.models} == set(ModelClass)
    assert not any(item.enabled for item in DEFAULT_MODEL_CATALOG.models)
    assert not any(item.enabled for item in DEFAULT_MODEL_CATALOG.providers)


def test_catalog_rejects_duplicate_provider_and_model_identifiers() -> None:
    provider = ProviderDefinition(key="provider")
    base_model = model(
        "provider",
        "model",
        ModelClass.FAST,
        QualityTier.FAST,
        capabilities=frozenset({ModelCapability.TEXT_GENERATION}),
        context_limit=100,
        output_limit=10,
    )
    with pytest.raises(ValueError, match="Duplicate provider"):
        ModelCatalog((provider, provider), (base_model,))
    with pytest.raises(ValueError, match="Duplicate model"):
        ModelCatalog((provider,), (base_model, base_model))


def test_catalog_rejects_model_with_unknown_provider() -> None:
    orphan = model(
        "missing",
        "model",
        ModelClass.FAST,
        QualityTier.FAST,
        capabilities=frozenset({ModelCapability.TEXT_GENERATION}),
        context_limit=100,
        output_limit=10,
    )
    with pytest.raises(ValueError, match="unknown provider"):
        ModelCatalog((ProviderDefinition(key="known"),), (orphan,))


def test_model_limits_and_specialized_capabilities_are_validated() -> None:
    common = {
        "provider_key": "provider",
        "model_id": "model",
        "enabled": True,
        "max_sensitivity": DataSensitivity.PUBLIC,
        "quality_tier": QualityTier.SPECIALIZED,
        "latency_tier": LatencyTier.NORMAL,
        "pricing": pricing(1, 1),
    }
    with pytest.raises(ValidationError):
        ModelDefinition.model_validate(
            {
                **common,
                "model_class": ModelClass.FAST,
                "capabilities": frozenset({ModelCapability.TEXT_GENERATION}),
                "context_limit": 10,
                "output_limit": 11,
            }
        )
    with pytest.raises(ValidationError, match="Realtime"):
        ModelDefinition.model_validate(
            {
                **common,
                "model_class": ModelClass.REALTIME,
                "capabilities": frozenset({ModelCapability.TEXT_GENERATION}),
                "context_limit": 10,
                "output_limit": 1,
            }
        )
    with pytest.raises(ValidationError, match="Embedding"):
        ModelDefinition.model_validate(
            {
                **common,
                "model_class": ModelClass.EMBEDDING,
                "capabilities": frozenset({ModelCapability.TEXT_GENERATION}),
                "context_limit": 10,
                "output_limit": 1,
            }
        )


def test_pricing_metadata_estimates_but_never_claims_actual_cost() -> None:
    price = PricingMetadata(
        currency="USD",
        input_microunits_per_million_tokens=100_000,
        output_microunits_per_million_tokens=200_000,
        pricing_version="test",
        effective_date=date(2026, 9, 1),
    )
    assert price.estimate_microunits(1_000, 1_000) == 300


def test_sensitive_approval_requires_conservative_provider_chain() -> None:
    with pytest.raises(ValidationError, match="private-data"):
        ProviderDefinition(
            key="unsafe",
            enabled=True,
            max_sensitivity=DataSensitivity.SENSITIVE,
            sensitive_data_approved=True,
        )
    with pytest.raises(ValidationError, match="local"):
        ProviderDefinition(
            key="unsafe-critical",
            enabled=True,
            max_sensitivity=DataSensitivity.CRITICAL,
            private_data_approved=True,
            sensitive_data_approved=True,
            critical_data_approved=True,
        )


def test_fake_provider_and_registry_are_deterministic_and_classified() -> None:
    response = ProviderResponse(output_text="ok", input_tokens=1, output_tokens=1)
    fake = FakeProvider("primary", (FailureCategory.TIMEOUT, response))
    registry = ProviderRegistry((fake,))
    request = ProviderRequest(input_text="private prompt", output_token_budget=10)

    async def scenario() -> None:
        with pytest.raises(ProviderFailure) as failure:
            await registry.get("primary").generate("model", request)
        assert failure.value.category is FailureCategory.TIMEOUT
        assert failure.value.retryable is True
        assert await registry.get("primary").generate("model", request) == response

    asyncio.run(scenario())


def test_provider_registry_rejects_duplicates_and_missing_adapter() -> None:
    first = FakeProvider("same", ())
    with pytest.raises(ValueError, match="Duplicate provider"):
        ProviderRegistry((first, first))
    with pytest.raises(ProviderFailure) as failure:
        ProviderRegistry(()).get("not-configured")
    assert failure.value.category is FailureCategory.PROVIDER_UNAVAILABLE


def test_phase5_fixture_catalog_is_server_owned_and_complete() -> None:
    catalog = routing_catalog()
    assert catalog.provider("primary").private_data_approved is True
    advanced = next(item for item in catalog.models if item.model_id == "advanced")
    assert (
        catalog.model(ModelReference.from_definition(advanced)).quality_tier is QualityTier.ADVANCED
    )


@pytest.mark.parametrize(
    "category",
    [
        FailureCategory.PROVIDER_UNAVAILABLE,
        FailureCategory.RATE_LIMITED,
        FailureCategory.TIMEOUT,
        FailureCategory.INTERNAL_PROVIDER_ERROR,
    ],
)
def test_transient_failure_categories_are_retryable(category: FailureCategory) -> None:
    assert is_retryable_failure(category) is True


@pytest.mark.parametrize(
    "category",
    [
        FailureCategory.AUTHENTICATION_ERROR,
        FailureCategory.INVALID_REQUEST,
        FailureCategory.CONTEXT_LIMIT,
        FailureCategory.CONTENT_POLICY,
        FailureCategory.UNSUPPORTED_CAPABILITY,
        FailureCategory.MALFORMED_RESPONSE,
        FailureCategory.CANCELLED,
    ],
)
def test_permanent_failure_categories_are_not_retryable(category: FailureCategory) -> None:
    assert is_retryable_failure(category) is False
