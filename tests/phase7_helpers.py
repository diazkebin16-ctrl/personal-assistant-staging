"""Deterministic Text Assistant composition with no network or live credentials."""

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai_router.policy import AIRoutingPolicy
from backend.app.ai_router.provider import FakeProvider, ProviderRegistry
from backend.app.ai_router.schemas import ProviderResponse
from backend.app.ai_router.service import AIRouter
from backend.app.orchestrator.enums import SafeMode
from backend.app.text_assistant.service import TextAssistantService
from tests.phase5_helpers import routing_catalog
from tests.phase6_helpers import build_orchestrator


def build_text_assistant(
    session: AsyncSession,
    chat_outcomes: Iterable[ProviderResponse],
    *,
    orchestration_outcomes: Iterable[ProviderResponse] = (),
    safe_mode: SafeMode = SafeMode.NORMAL,
) -> tuple[TextAssistantService, dict[str, FakeProvider], dict[str, FakeProvider]]:
    orchestrator, orchestration_providers = build_orchestrator(
        session,
        orchestration_outcomes,
        safe_mode=safe_mode,
    )
    catalog = routing_catalog()
    responses = tuple(chat_outcomes)
    providers = {
        key: FakeProvider(key, responses)
        for key in ("primary", "equivalent", "sensitive-approved", "local-approved")
    }
    router = AIRouter(
        session,
        catalog,
        AIRoutingPolicy(catalog),
        providers=ProviderRegistry(providers.values()),
    )
    return (
        TextAssistantService(session, orchestrator.memory, router, orchestrator),
        providers,
        orchestration_providers,
    )
