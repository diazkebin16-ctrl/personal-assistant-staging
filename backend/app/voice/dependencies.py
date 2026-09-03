"""FastAPI composition for Voice without provider credentials or client routing control."""

from typing import Annotated

from fastapi import Depends

from backend.app.ai_router.catalog import DEFAULT_MODEL_CATALOG
from backend.app.ai_router.policy import AIRoutingPolicy
from backend.app.ai_router.service import AIRouter
from backend.app.core.config import Settings, get_settings
from backend.app.identity.dependencies import DatabaseSession
from backend.app.text_assistant.dependencies import TextAssistantDependency
from backend.app.voice.provider import RealtimeProviderRegistry
from backend.app.voice.service import VoiceSessionPolicy, VoiceSessionService

DEFAULT_REALTIME_PROVIDERS = RealtimeProviderRegistry()


def get_realtime_provider_registry() -> RealtimeProviderRegistry:
    """No live adapter is enabled until deployment supplies approved server configuration."""
    return DEFAULT_REALTIME_PROVIDERS


RealtimeProvidersDependency = Annotated[
    RealtimeProviderRegistry, Depends(get_realtime_provider_registry)
]


def get_voice_service(
    session: DatabaseSession,
    text_assistant: TextAssistantDependency,
    providers: RealtimeProvidersDependency,
    settings: Annotated[Settings, Depends(get_settings)],
) -> VoiceSessionService:
    router = AIRouter(
        session,
        DEFAULT_MODEL_CATALOG,
        AIRoutingPolicy(DEFAULT_MODEL_CATALOG),
    )
    policy = VoiceSessionPolicy(
        credential_ttl_seconds=settings.voice_credential_ttl_seconds,
        connection_timeout_seconds=settings.voice_connection_timeout_seconds,
        idle_timeout_seconds=settings.voice_idle_timeout_seconds,
        max_session_seconds=settings.voice_max_session_seconds,
        max_reconnect_attempts=settings.voice_max_reconnect_attempts,
        voice_profile=settings.voice_profile,
    )
    return VoiceSessionService(session, text_assistant, router, providers, policy=policy)


VoiceServiceDependency = Annotated[VoiceSessionService, Depends(get_voice_service)]
