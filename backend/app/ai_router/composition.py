"""Server-side composition of configured OpenAI components."""

from backend.app.ai_router.catalog import ModelCatalog, build_staging_catalog
from backend.app.ai_router.openai_provider import OpenAIProvider
from backend.app.ai_router.provider import LLMProvider, ProviderRegistry
from backend.app.core.config import Settings


def build_configured_ai_components(settings: Settings) -> tuple[ModelCatalog, ProviderRegistry]:
    """Build the OpenAI runtime boundary from the optional server-side credential."""
    openai_enabled = settings.openai_api_key is not None
    catalog = build_staging_catalog(openai_enabled=openai_enabled)

    providers: list[LLMProvider] = []
    if settings.openai_api_key is not None:
        providers.append(OpenAIProvider(settings.openai_api_key.get_secret_value()))

    return catalog, ProviderRegistry(providers)
