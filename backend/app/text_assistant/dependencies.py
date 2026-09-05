"""FastAPI composition for Text Assistant without a public provider/model control."""

from typing import Annotated

from fastapi import Depends

from backend.app.ai_router.composition import build_configured_ai_components
from backend.app.ai_router.policy import AIRoutingPolicy
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
    catalog, providers = build_configured_ai_components(settings)
    router = AIRouter(
        session,
        catalog,
        AIRoutingPolicy(catalog),
        providers=providers,
    )
    return TextAssistantService(session, memory, router, orchestrator)


TextAssistantDependency = Annotated[TextAssistantService, Depends(get_text_assistant_service)]
