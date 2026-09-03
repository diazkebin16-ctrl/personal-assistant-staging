"""FastAPI composition for Text Assistant without a public provider/model control."""

from typing import Annotated

from fastapi import Depends

from backend.app.ai_router.catalog import DEFAULT_MODEL_CATALOG, OPENAI_STAGING_CATALOG
from backend.app.ai_router.policy import AIRoutingPolicy
from backend.app.ai_router.openai_provider import OpenAIProvider
from backend.app.ai_router.provider import ProviderRegistry
from backend.app.ai_router.service import AIRouter
from backend.app.core.config import get_settings
from backend.app.identity.dependencies import DatabaseSession
from backend.app.memory.dependencies import MemoryServiceDependency
from backend.app.orchestrator.dependencies import OrchestratorDependency
from backend.app.text_assistant.service import TextAssistantService


def get_text_assistant_service(
    session: DatabaseSession,
    memory: MemoryServiceDependency,
    orchestrator: OrchestratorDependency,
) -> TextAssistantService:
    settings = get_settings()
    if settings.openai_api_key is None:
        catalog = DEFAULT_MODEL_CATALOG
        providers = ProviderRegistry(())
    else:
        catalog = OPENAI_STAGING_CATALOG
        providers = ProviderRegistry(
            (OpenAIProvider(settings.openai_api_key.get_secret_value()),)
        )

    router = AIRouter(
        session,
        catalog,
        AIRoutingPolicy(catalog),
        providers=providers,
    )
    return TextAssistantService(session, memory, router, orchestrator)


TextAssistantDependency = Annotated[TextAssistantService, Depends(get_text_assistant_service)]
