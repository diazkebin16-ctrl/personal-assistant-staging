"""FastAPI wiring for the internal Orchestrator composition boundary."""

from typing import Annotated

from fastapi import Depends

from backend.app.ai_router.composition import build_configured_ai_components
from backend.app.ai_router.policy import AIRoutingPolicy
from backend.app.ai_router.service import AIRouter
from backend.app.core.config import Settings, get_settings
from backend.app.identity.dependencies import DatabaseSession
from backend.app.memory.dependencies import MemoryServiceDependency
from backend.app.orchestrator.enums import SafeMode
from backend.app.orchestrator.policy import OrchestratorFeatures, OrchestratorPolicy
from backend.app.orchestrator.service import OrchestratorService
from backend.app.permissions.dependencies import AuditEngineDependency
from backend.app.research.fetch import SafeFetcher
from backend.app.research.policy import ResearchPolicy
from backend.app.research.provider import SearchProviderRegistry
from backend.app.research.service import ResearchService
from backend.app.research.url_safety import URLSafetyPolicy
from backend.app.tasks.dependencies import TaskServiceDependency


def get_orchestrator_service(
    session: DatabaseSession,
    memory: MemoryServiceDependency,
    tasks: TaskServiceDependency,
    audit: AuditEngineDependency,
    settings: Annotated[Settings, Depends(get_settings)],
) -> OrchestratorService:
    catalog, providers = build_configured_ai_components(settings)
    router = AIRouter(
        session,
        catalog,
        AIRoutingPolicy(catalog),
        providers=providers,
    )
    policy = OrchestratorPolicy(
        safe_mode=SafeMode(settings.orchestrator_mode),
        features=OrchestratorFeatures(
            ai_enabled=settings.orchestrator_ai_enabled,
            action_workflows_enabled=settings.orchestrator_actions_enabled,
        ),
    )
    research = ResearchService(
        router,
        tasks.permissions,
        audit,
        ResearchPolicy(enabled=settings.research_enabled, safe_mode=policy.safe_mode),
        SearchProviderRegistry((), environment=settings.environment),
        SafeFetcher(URLSafetyPolicy()),
    )
    return OrchestratorService(
        session,
        memory,
        router,
        tasks,
        audit,
        policy,
        research_service=research,
    )


OrchestratorDependency = Annotated[OrchestratorService, Depends(get_orchestrator_service)]
