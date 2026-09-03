"""Validated, immutable server-owned model catalog."""

from collections.abc import Iterable
from datetime import date
from types import MappingProxyType

from backend.app.ai_router.enums import (
    LatencyTier,
    ModelCapability,
    ModelClass,
    QualityTier,
)
from backend.app.ai_router.schemas import (
    ModelDefinition,
    ModelReference,
    PricingMetadata,
    ProviderDefinition,
)
from backend.app.security.classification import DataSensitivity


class ModelCatalog:
    """Single authoritative model vocabulary with no client mutation surface."""

    def __init__(
        self,
        providers: Iterable[ProviderDefinition],
        models: Iterable[ModelDefinition],
    ) -> None:
        provider_map: dict[str, ProviderDefinition] = {}
        for provider in providers:
            if provider.key in provider_map:
                raise ValueError(f"Duplicate provider key: {provider.key}")
            provider_map[provider.key] = provider

        model_map: dict[tuple[str, str], ModelDefinition] = {}
        for model in models:
            key = (model.provider_key, model.model_id)
            if key in model_map:
                raise ValueError(
                    f"Duplicate model identifier: {model.provider_key}/{model.model_id}"
                )
            if model.provider_key not in provider_map:
                raise ValueError(f"Model references an unknown provider: {model.provider_key}")
            model_map[key] = model

        if not provider_map:
            raise ValueError("The model catalog requires at least one provider definition")
        if not model_map:
            raise ValueError("The model catalog requires at least one model definition")
        self._providers = MappingProxyType(provider_map)
        self._models = MappingProxyType(model_map)

    @property
    def providers(self) -> tuple[ProviderDefinition, ...]:
        return tuple(self._providers.values())

    @property
    def models(self) -> tuple[ModelDefinition, ...]:
        return tuple(self._models.values())

    def provider(self, provider_key: str) -> ProviderDefinition:
        try:
            return self._providers[provider_key]
        except KeyError:
            raise KeyError(f"Unknown provider: {provider_key}") from None

    def model(self, reference: ModelReference) -> ModelDefinition:
        try:
            return self._models[(reference.provider_key, reference.model_id)]
        except KeyError:
            raise KeyError(
                f"Unknown model: {reference.provider_key}/{reference.model_id}"
            ) from None


_RESERVED_PRICING = PricingMetadata(
    currency="USD",
    input_microunits_per_million_tokens=250_000,
    output_microunits_per_million_tokens=1_000_000,
    pricing_version="phase5-reserved-not-live",
    effective_date=date(2026, 9, 1),
)


def build_default_catalog() -> ModelCatalog:
    """Return disabled placeholders; no provider is operational without explicit configuration."""
    providers = (
        ProviderDefinition(
            key="cloud-reserved",
            enabled=False,
            max_sensitivity=DataSensitivity.PUBLIC,
        ),
        ProviderDefinition(
            key="local-reserved",
            enabled=False,
            local=True,
            max_sensitivity=DataSensitivity.CRITICAL,
            private_data_approved=True,
            sensitive_data_approved=True,
            critical_data_approved=True,
        ),
    )
    models = (
        ModelDefinition(
            provider_key="cloud-reserved",
            model_id="fast-reserved",
            model_class=ModelClass.FAST,
            enabled=False,
            capabilities=frozenset(
                {ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_OUTPUT}
            ),
            context_limit=16_384,
            output_limit=4_096,
            max_sensitivity=DataSensitivity.PUBLIC,
            quality_tier=QualityTier.FAST,
            latency_tier=LatencyTier.LOW,
            pricing=_RESERVED_PRICING,
        ),
        ModelDefinition(
            provider_key="cloud-reserved",
            model_id="standard-reserved",
            model_class=ModelClass.STANDARD,
            enabled=False,
            capabilities=frozenset(
                {
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.STRUCTURED_OUTPUT,
                    ModelCapability.TOOL_CALLING,
                    ModelCapability.STREAMING,
                }
            ),
            context_limit=65_536,
            output_limit=16_384,
            max_sensitivity=DataSensitivity.PUBLIC,
            quality_tier=QualityTier.STANDARD,
            latency_tier=LatencyTier.NORMAL,
            pricing=_RESERVED_PRICING,
        ),
        ModelDefinition(
            provider_key="cloud-reserved",
            model_id="advanced-reserved",
            model_class=ModelClass.ADVANCED,
            enabled=False,
            capabilities=frozenset(
                {
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.STRUCTURED_OUTPUT,
                    ModelCapability.TOOL_CALLING,
                    ModelCapability.STREAMING,
                }
            ),
            context_limit=131_072,
            output_limit=32_768,
            max_sensitivity=DataSensitivity.PUBLIC,
            quality_tier=QualityTier.ADVANCED,
            latency_tier=LatencyTier.HIGH,
            pricing=_RESERVED_PRICING,
        ),
        ModelDefinition(
            provider_key="cloud-reserved",
            model_id="realtime-reserved",
            model_class=ModelClass.REALTIME,
            enabled=False,
            capabilities=frozenset(
                {ModelCapability.AUDIO_REALTIME, ModelCapability.TEXT_GENERATION}
            ),
            context_limit=32_768,
            output_limit=4_096,
            max_sensitivity=DataSensitivity.PUBLIC,
            quality_tier=QualityTier.SPECIALIZED,
            latency_tier=LatencyTier.LOW,
            pricing=_RESERVED_PRICING,
        ),
        ModelDefinition(
            provider_key="cloud-reserved",
            model_id="embedding-reserved",
            model_class=ModelClass.EMBEDDING,
            enabled=False,
            capabilities=frozenset({ModelCapability.EMBEDDINGS}),
            context_limit=32_768,
            output_limit=1,
            max_sensitivity=DataSensitivity.PUBLIC,
            quality_tier=QualityTier.SPECIALIZED,
            latency_tier=LatencyTier.NORMAL,
            pricing=_RESERVED_PRICING,
        ),
        ModelDefinition(
            provider_key="local-reserved",
            model_id="local-reserved",
            model_class=ModelClass.LOCAL,
            enabled=False,
            capabilities=frozenset(
                {ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_OUTPUT}
            ),
            context_limit=32_768,
            output_limit=8_192,
            max_sensitivity=DataSensitivity.CRITICAL,
            quality_tier=QualityTier.STANDARD,
            latency_tier=LatencyTier.NORMAL,
            pricing=_RESERVED_PRICING,
        ),
    )
    return ModelCatalog(providers, models)


DEFAULT_MODEL_CATALOG = build_default_catalog()
