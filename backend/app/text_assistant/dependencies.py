"""FastAPI composition for Text Assistant without a public provider/model control."""

from typing import Annotated

from fastapi import Depends

from backend.app.ai_router.catalog import DEFAULT_MODEL_CATALOG
from backend.app.ai_router.policy import AIRoutingPolicy
from backend.app.ai_router.service import AIRouter
from backend.app.identity.dependencies import DatabaseSession
from backend.app.memory.dependencies import MemoryServiceDependency
from backend.app.orchestrator.dependencies import OrchestratorDependency
from backend.app.text_assistant.service import TextAssistantService


def get_text_assistant_service(
    session: DatabaseSession,
    memory: MemoryServiceDependency,
    orchestrator: OrchestratorDependency,
) -> TextAssistantService:
    router = AIRouter(session, DEFAULT_MODEL_CATALOG, AIRoutingPolicy(DEFAULT_MODEL_CATALOG))
    return TextAssistantService(session, memory, router, orchestrator)


TextAssistantDependency = Annotated[TextAssistantService, Depends(get_text_assistant_service)]
