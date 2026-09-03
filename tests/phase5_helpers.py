"""Server-owned AI Router catalog and identity fixtures for Phase 5 tests."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from backend.app.ai_router.catalog import ModelCatalog
from backend.app.ai_router.enums import (
    LatencyTier,
    ModelCapability,
    ModelClass,
    QualityTier,
)
from backend.app.ai_router.schemas import ModelDefinition, PricingMetadata, ProviderDefinition
from backend.app.identity.context import AuthenticationLevel, IdentityContext
from backend.app.security.classification import DataSensitivity


def pricing(input_rate: int, output_rate: int, version: str = "test-v1") -> PricingMetadata:
    return PricingMetadata(
        currency="USD",
        input_microunits_per_million_tokens=input_rate,
        output_microunits_per_million_tokens=output_rate,
        pricing_version=version,
        effective_date=date(2026, 9, 1),
    )


def model(
    provider: str,
    model_id: str,
    model_class: ModelClass,
    quality: QualityTier,
    *,
    capabilities: frozenset[ModelCapability],
    context_limit: int,
    output_limit: int,
    sensitivity: DataSensitivity = DataSensitivity.PRIVATE,
    enabled: bool = True,
    deprecated: bool = False,
    input_rate: int = 100_000,
    output_rate: int = 200_000,
    fallback_priority: int = 100,
) -> ModelDefinition:
    return ModelDefinition(
        provider_key=provider,
        model_id=model_id,
        model_class=model_class,
        enabled=enabled,
        capabilities=capabilities,
        context_limit=context_limit,
        output_limit=output_limit,
        max_sensitivity=sensitivity,
        quality_tier=quality,
        latency_tier=LatencyTier.NORMAL,
        pricing=pricing(input_rate, output_rate),
        deprecated=deprecated,
        fallback_priority=fallback_priority,
    )


def routing_catalog() -> ModelCatalog:
    text = frozenset({ModelCapability.TEXT_GENERATION})
    structured = frozenset({ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_OUTPUT})
    tools = frozenset(
        {
            ModelCapability.TEXT_GENERATION,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
        }
    )
    providers = (
        ProviderDefinition(
            key="primary",
            enabled=True,
            max_sensitivity=DataSensitivity.PRIVATE,
            private_data_approved=True,
        ),
        ProviderDefinition(
            key="equivalent",
            enabled=True,
            max_sensitivity=DataSensitivity.PRIVATE,
            private_data_approved=True,
        ),
        ProviderDefinition(
            key="sensitive-approved",
            enabled=True,
            max_sensitivity=DataSensitivity.SENSITIVE,
            private_data_approved=True,
            sensitive_data_approved=True,
        ),
        ProviderDefinition(
            key="local-approved",
            enabled=True,
            local=True,
            max_sensitivity=DataSensitivity.CRITICAL,
            private_data_approved=True,
            sensitive_data_approved=True,
            critical_data_approved=True,
        ),
        ProviderDefinition(key="disabled", enabled=False),
    )
    models = (
        model(
            "primary",
            "fast",
            ModelClass.FAST,
            QualityTier.FAST,
            capabilities=structured,
            context_limit=8_192,
            output_limit=2_048,
            fallback_priority=10,
        ),
        model(
            "equivalent",
            "fast-equivalent",
            ModelClass.FAST,
            QualityTier.FAST,
            capabilities=structured,
            context_limit=8_192,
            output_limit=2_048,
            input_rate=120_000,
            output_rate=220_000,
            fallback_priority=20,
        ),
        model(
            "primary",
            "standard",
            ModelClass.STANDARD,
            QualityTier.STANDARD,
            capabilities=tools,
            context_limit=32_768,
            output_limit=8_192,
            input_rate=300_000,
            output_rate=600_000,
            fallback_priority=10,
        ),
        model(
            "equivalent",
            "standard-equivalent",
            ModelClass.STANDARD,
            QualityTier.STANDARD,
            capabilities=tools,
            context_limit=32_768,
            output_limit=8_192,
            input_rate=320_000,
            output_rate=620_000,
            fallback_priority=20,
        ),
        model(
            "primary",
            "advanced",
            ModelClass.ADVANCED,
            QualityTier.ADVANCED,
            capabilities=tools,
            context_limit=131_072,
            output_limit=32_768,
            input_rate=1_000_000,
            output_rate=2_000_000,
            fallback_priority=10,
        ),
        model(
            "equivalent",
            "advanced-equivalent",
            ModelClass.ADVANCED,
            QualityTier.ADVANCED,
            capabilities=tools,
            context_limit=131_072,
            output_limit=32_768,
            input_rate=1_100_000,
            output_rate=2_100_000,
            fallback_priority=20,
        ),
        model(
            "sensitive-approved",
            "sensitive-standard",
            ModelClass.STANDARD,
            QualityTier.STANDARD,
            capabilities=tools,
            context_limit=32_768,
            output_limit=8_192,
            sensitivity=DataSensitivity.SENSITIVE,
        ),
        model(
            "primary",
            "realtime",
            ModelClass.REALTIME,
            QualityTier.SPECIALIZED,
            capabilities=frozenset(
                {ModelCapability.AUDIO_REALTIME, ModelCapability.TEXT_GENERATION}
            ),
            context_limit=16_384,
            output_limit=4_096,
        ),
        model(
            "primary",
            "embedding",
            ModelClass.EMBEDDING,
            QualityTier.SPECIALIZED,
            capabilities=frozenset({ModelCapability.EMBEDDINGS}),
            context_limit=16_384,
            output_limit=1,
        ),
        model(
            "local-approved",
            "local",
            ModelClass.LOCAL,
            QualityTier.ADVANCED,
            capabilities=structured,
            context_limit=32_768,
            output_limit=8_192,
            sensitivity=DataSensitivity.CRITICAL,
        ),
        model(
            "disabled",
            "hidden-model",
            ModelClass.FAST,
            QualityTier.FAST,
            capabilities=text,
            context_limit=8_192,
            output_limit=2_048,
        ),
    )
    return ModelCatalog(providers, models)


def identity(user_id: UUID | None = None) -> IdentityContext:
    return IdentityContext(
        user_id=user_id or uuid4(),
        auth_user_id=uuid4(),
        device_id=None,
        session_id=None,
        display_name="Router Test",
        authentication_level=AuthenticationLevel.AAL2,
        token_expiry=datetime.now(UTC) + timedelta(hours=1),
    )
