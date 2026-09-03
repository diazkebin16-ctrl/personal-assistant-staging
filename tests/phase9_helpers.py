"""Deterministic Realtime Voice composition with local fake providers only."""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai_router.catalog import ModelCatalog
from backend.app.ai_router.enums import ModelCapability, ModelClass, QualityTier
from backend.app.ai_router.policy import AIRoutingPolicy
from backend.app.ai_router.service import AIRouter
from backend.app.identity.context import IdentityContext
from backend.app.identity.models import AuthSession, Device, DeviceType
from backend.app.orchestrator.enums import SafeMode
from backend.app.security.classification import DataSensitivity
from backend.app.text_assistant.models import Conversation
from backend.app.text_assistant.schemas import ConversationCreateRequest
from backend.app.voice.provider import (
    FakeRealtimeProvider,
    RealtimeProviderEvent,
    RealtimeProviderRegistry,
)
from backend.app.voice.schemas import ProviderAudioEvent
from backend.app.voice.service import VoiceSessionPolicy, VoiceSessionService
from tests.phase5_helpers import identity, model, routing_catalog
from tests.phase6_helpers import add_identity_user, provider_response
from tests.phase7_helpers import build_text_assistant


async def voice_identity(session: AsyncSession) -> IdentityContext:
    base = identity()
    await add_identity_user(session, base)
    device = Device(
        user_id=base.user_id,
        device_name="Voice test phone",
        device_type=DeviceType.ANDROID,
        platform="android-35",
        device_identifier=f"android:{uuid4()}",
        capabilities={"microphone": True},
    )
    session.add(device)
    await session.flush()
    auth_session = AuthSession(
        user_id=base.user_id,
        device_id=device.id,
        auth_session_identifier=f"voice-test-{uuid4()}",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(auth_session)
    await session.flush()
    return base.model_copy(
        update={
            "device_id": device.id,
            "session_id": auth_session.id,
            "token_expiry": auth_session.expires_at,
        }
    )


def realtime_catalog() -> ModelCatalog:
    base = routing_catalog()
    local_realtime = model(
        "local-approved",
        "local-realtime",
        ModelClass.REALTIME,
        QualityTier.SPECIALIZED,
        capabilities=frozenset({ModelCapability.AUDIO_REALTIME, ModelCapability.TEXT_GENERATION}),
        context_limit=32_768,
        output_limit=4_096,
        sensitivity=DataSensitivity.CRITICAL,
        fallback_priority=1,
    )
    return ModelCatalog(base.providers, (*base.models, local_realtime))


async def build_voice_service(
    session: AsyncSession,
    input_events: Iterable[tuple[RealtimeProviderEvent, ...]],
    audio_events: Iterable[tuple[ProviderAudioEvent, ...]],
    *,
    chat_responses: Iterable[str] = ("Voice response",),
    orchestration_responses: Iterable[str] = (),
    policy: VoiceSessionPolicy | None = None,
    safe_mode: SafeMode = SafeMode.NORMAL,
) -> tuple[VoiceSessionService, FakeRealtimeProvider]:
    text, _, _ = build_text_assistant(
        session,
        tuple(provider_response(item) for item in chat_responses),
        orchestration_outcomes=tuple(provider_response(item) for item in orchestration_responses),
        safe_mode=safe_mode,
    )
    catalog = realtime_catalog()
    router = AIRouter(session, catalog, AIRoutingPolicy(catalog))
    realtime = FakeRealtimeProvider("local-approved", input_events, audio_events)
    voice = VoiceSessionService(
        session,
        text,
        router,
        RealtimeProviderRegistry((realtime,)),
        policy=policy,
    )
    return voice, realtime


async def create_voice_conversation(
    service: VoiceSessionService, identity_context: IdentityContext
) -> Conversation:
    return await service.text_assistant.create_conversation(
        identity_context, ConversationCreateRequest(title="Voice conversation")
    )
