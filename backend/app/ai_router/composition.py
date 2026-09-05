"""Server-side composition of configured AI providers and the staging catalog."""

from backend.app.ai_router.catalog import ModelCatalog, build_staging_catalog
from backend.app.ai_router.gemini_provider import GeminiProvider
from backend.app.ai_router.openai_provider import OpenAIProvider
from backend.app.ai_router.provider import LLMProvider, ProviderRegistry
from backend.app.core.config import Settings


def build_configured_ai_components(settings: Settings) -> tuple[ModelCatalog, ProviderRegistry]:
    """Build provider-neutral runtime components from independently optional credentials."""
    openai_enabled = settings.openai_api_key is not None
    gemini_enabled = settings.gemini_api_key is not None
    catalog = build_staging_catalog(
        openai_enabled=openai_enabled,
        gemini_enabled=gemini_enabled,
    )

    providers: list[LLMProvider] = []
    if settings.openai_api_key is not None:
        providers.append(OpenAIProvider(settings.openai_api_key.get_secret_value()))
    if settings.gemini_api_key is not None:
        providers.append(GeminiProvider(settings.gemini_api_key.get_secret_value()))

    return catalog, ProviderRegistry(providers)
