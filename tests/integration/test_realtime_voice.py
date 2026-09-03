"""Phase 9 realtime session, transcript bridge, reconnect, and barge-in flows."""

import asyncio
import base64
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from backend.app.core.errors import (
    ConversationNotFoundError,
    VoiceReconnectExhaustedError,
    VoiceSessionAuthFailedError,
    VoiceSessionConflictError,
    VoiceSessionExpiredError,
    VoiceTurnIdempotencyConflictError,
)
from backend.app.identity.context import IdentityContext
from backend.app.identity.models import utc_now
from backend.app.memory.models import MemoryRecord
from backend.app.orchestrator.enums import SafeMode
from backend.app.tasks.models import Task
from backend.app.text_assistant.enums import AssistantOutcome
from backend.app.text_assistant.models import Conversation, ConversationMessage
from backend.app.voice.enums import (
    TranscriptKind,
    VoiceClientEventType,
    VoiceServerEventType,
    VoiceSessionState,
)
from backend.app.voice.models import VoiceSession, VoiceTurn
from backend.app.voice.protocol import MalformedVoiceEventError, VoiceProtocolCoordinator
from backend.app.voice.provider import FakeRealtimeConnection, FakeRealtimeProvider
from backend.app.voice.schemas import (
    AudioFrameEvent,
    InterruptEvent,
    PlaybackCompletedEvent,
    ProviderAudioEvent,
    ProviderTranscriptEvent,
    VoiceSessionCreateRequest,
    VoiceSessionResponse,
)
from backend.app.voice.service import VoiceSessionPolicy, VoiceSessionService
from tests.helpers import isolated_database
from tests.phase6_helpers import candidate_plan, grant
from tests.phase9_helpers import (
    build_voice_service,
    create_voice_conversation,
    voice_identity,
)


def audio_event(turn_id: str, *, final: bool = True) -> ProviderAudioEvent:
    return ProviderAudioEvent(
        turn_id=turn_id,
        sequence=0,
        audio=b"\x01\x00" * 480,
        final=final,
    )


def frame(turn_id: str, sequence: int) -> AudioFrameEvent:
    return AudioFrameEvent(
        type=VoiceClientEventType.AUDIO_FRAME,
        turn_id=turn_id,
        sequence=sequence,
        audio_b64=base64.b64encode(b"\x01\x00" * 480).decode(),
    )


async def started(
    service: VoiceSessionService,
    realtime: FakeRealtimeProvider,
    current: IdentityContext,
    conversation: Conversation,
    turn_id: str,
) -> tuple[VoiceProtocolCoordinator, VoiceSessionResponse]:
    del turn_id
    response = await service.start(
        current,
        VoiceSessionCreateRequest(conversation_id=conversation.id),
    )
    access = await service.open_connection(response.id, response.credential)
    connection = await realtime.connect(access.model_id, access.voice_profile)
    return VoiceProtocolCoordinator(service, access, connection), response


def test_realtime_voice_end_to_end_partial_final_text_audio_and_persistence() -> None:
    async def scenario() -> None:
        turn_id = "voice-turn-e2e-0001"
        partial = ProviderTranscriptEvent(
            turn_id=turn_id,
            kind=TranscriptKind.PARTIAL,
            text="Hola asis",
            confidence=0.7,
        )
        final = ProviderTranscriptEvent(
            turn_id=turn_id,
            kind=TranscriptKind.FINAL,
            text="Hola asistente",
            confidence=0.98,
        )
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = await voice_identity(session)
                service, realtime = await build_voice_service(
                    session,
                    ((partial,), (final,)),
                    ((audio_event(turn_id),),),
                    chat_responses=("Hola. ¿En qué puedo ayudarte?",),
                )
                conversation = await create_voice_conversation(service, current)
                coordinator, _ = await started(service, realtime, current, conversation, turn_id)

                partial_result = await coordinator.handle(frame(turn_id, 0))
                assert [item.type for item in partial_result] == [VoiceServerEventType.TRANSCRIPT]
                assert await session.scalar(select(func.count()).select_from(VoiceTurn)) == 0
                assert (
                    await session.scalar(select(func.count()).select_from(ConversationMessage)) == 0
                )
                assert await session.scalar(select(func.count()).select_from(MemoryRecord)) == 0
                assert await session.scalar(select(func.count()).select_from(Task)) == 0

                final_result = await coordinator.handle(frame(turn_id, 1))
                event_types = [item.type for item in final_result]
                assert event_types == [
                    VoiceServerEventType.TRANSCRIPT,
                    VoiceServerEventType.ASSISTANT_TEXT,
                    VoiceServerEventType.SESSION_STATE,
                    VoiceServerEventType.ASSISTANT_AUDIO,
                ]
                assert final_result[1].text == "Hola. ¿En qué puedo ayudarte?"
                assert final_result[2].state is VoiceSessionState.SPEAKING
                messages = list(
                    await session.scalars(
                        select(ConversationMessage).order_by(ConversationMessage.sequence)
                    )
                )
                assert [item.content for item in messages] == [
                    "Hola asistente",
                    "Hola. ¿En qué puedo ayudarte?",
                ]
                assert await session.scalar(select(func.count()).select_from(VoiceTurn)) == 1

    asyncio.run(scenario())


def test_partial_transcript_has_zero_authority_and_creates_no_task_memory_or_message() -> None:
    async def scenario() -> None:
        turn_id = "voice-partial-zero-authority"
        partial = ProviderTranscriptEvent(
            turn_id=turn_id,
            kind=TranscriptKind.PARTIAL,
            text="confirmo compra ahora",
        )
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = await voice_identity(session)
                service, realtime = await build_voice_service(session, ((partial,),), ())
                conversation = await create_voice_conversation(service, current)
                coordinator, _ = await started(service, realtime, current, conversation, turn_id)
                result = await coordinator.handle(frame(turn_id, 0))
                assert result[0].transcript_kind is TranscriptKind.PARTIAL
                assert await session.scalar(select(func.count()).select_from(VoiceTurn)) == 0
                assert (
                    await session.scalar(select(func.count()).select_from(ConversationMessage)) == 0
                )

    asyncio.run(scenario())


def test_final_turn_retry_is_idempotent_and_old_audio_is_not_replayed() -> None:
    async def scenario() -> None:
        turn_id = "voice-idempotent-turn"
        final = ProviderTranscriptEvent(
            turn_id=turn_id,
            kind=TranscriptKind.FINAL,
            text="Una sola respuesta",
        )
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = await voice_identity(session)
                service, realtime = await build_voice_service(
                    session,
                    ((final,),),
                    ((audio_event(turn_id),),),
                    chat_responses=("Una vez",),
                )
                conversation = await create_voice_conversation(service, current)
                first, response = await started(service, realtime, current, conversation, turn_id)
                first_events = await first.handle(frame(turn_id, 0))
                assert VoiceServerEventType.ASSISTANT_AUDIO in {item.type for item in first_events}
                await service.disconnect(first.access, end=False)

                access = await service.open_connection(response.id, response.credential)
                second_connection = await realtime.connect(access.model_id, access.voice_profile)
                second = VoiceProtocolCoordinator(service, access, second_connection)
                second_events = await second.handle(frame(turn_id, 0))
                assert VoiceServerEventType.ASSISTANT_AUDIO not in {
                    item.type for item in second_events
                }
                assert await session.scalar(select(func.count()).select_from(VoiceTurn)) == 1
                assert (
                    await session.scalar(select(func.count()).select_from(ConversationMessage)) == 2
                )

    asyncio.run(scenario())


def test_same_turn_identity_with_changed_final_transcript_conflicts() -> None:
    async def scenario() -> None:
        turn_id = "voice-changed-turn"
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = await voice_identity(session)
                service, realtime = await build_voice_service(
                    session,
                    (),
                    (),
                    chat_responses=("first",),
                )
                conversation = await create_voice_conversation(service, current)
                coordinator, _ = await started(service, realtime, current, conversation, turn_id)
                await service.finalize_turn(coordinator.access, turn_id, "first transcript", 1.0)
                with pytest.raises(VoiceTurnIdempotencyConflictError):
                    await service.finalize_turn(
                        coordinator.access, turn_id, "changed transcript", 1.0
                    )

    asyncio.run(scenario())


def test_barge_in_cancels_provider_and_moves_to_listening_without_old_audio() -> None:
    async def scenario() -> None:
        turn_id = "voice-barge-in-turn"
        final = ProviderTranscriptEvent(
            turn_id=turn_id,
            kind=TranscriptKind.FINAL,
            text="Háblame",
        )
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = await voice_identity(session)
                service, realtime = await build_voice_service(
                    session,
                    ((final,),),
                    ((audio_event(turn_id),),),
                    chat_responses=("Respuesta larga",),
                )
                conversation = await create_voice_conversation(service, current)
                coordinator, _ = await started(service, realtime, current, conversation, turn_id)
                await coordinator.handle(frame(turn_id, 0))
                result = await coordinator.handle(
                    InterruptEvent(type=VoiceClientEventType.INTERRUPT, turn_id=turn_id)
                )
                assert isinstance(coordinator.provider, FakeRealtimeConnection)
                assert coordinator.provider.interrupted_turns == [turn_id]
                assert result[-1].state is VoiceSessionState.LISTENING

    asyncio.run(scenario())


def test_cross_turn_interrupt_and_playback_completion_are_rejected() -> None:
    async def scenario() -> None:
        turn_id = "voice-current-output-turn"
        final = ProviderTranscriptEvent(
            turn_id=turn_id,
            kind=TranscriptKind.FINAL,
            text="Respuesta actual",
        )
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = await voice_identity(session)
                service, realtime = await build_voice_service(
                    session,
                    ((final,),),
                    ((audio_event(turn_id),),),
                    chat_responses=("Respuesta",),
                )
                conversation = await create_voice_conversation(service, current)
                coordinator, _ = await started(service, realtime, current, conversation, turn_id)
                await coordinator.handle(frame(turn_id, 0))
                with pytest.raises(MalformedVoiceEventError, match="Cross-turn interruption"):
                    await coordinator.handle(
                        InterruptEvent(
                            type=VoiceClientEventType.INTERRUPT,
                            turn_id="voice-forged-other-turn",
                        )
                    )
                with pytest.raises(MalformedVoiceEventError, match="Cross-turn playback"):
                    await coordinator.handle(
                        PlaybackCompletedEvent(
                            type=VoiceClientEventType.PLAYBACK_COMPLETED,
                            turn_id="voice-forged-other-turn",
                        )
                    )
                assert (
                    await service.state_for_connection(coordinator.access)
                    is VoiceSessionState.SPEAKING
                )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "audio_response",
    [
        (
            ProviderAudioEvent(
                turn_id="voice-malformed-audio",
                sequence=1,
                audio=b"\x01\x00" * 480,
                final=True,
            ),
        ),
        (
            ProviderAudioEvent(
                turn_id="voice-malformed-audio",
                sequence=0,
                audio=b"\x01\x00" * 480,
                final=False,
            ),
        ),
    ],
    ids=("out-of-order", "missing-final"),
)
def test_provider_audio_ordering_and_termination_fail_closed(
    audio_response: tuple[ProviderAudioEvent, ...],
) -> None:
    async def scenario() -> None:
        turn_id = "voice-malformed-audio"
        final = ProviderTranscriptEvent(
            turn_id=turn_id,
            kind=TranscriptKind.FINAL,
            text="Prueba de audio",
        )
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = await voice_identity(session)
                service, realtime = await build_voice_service(
                    session,
                    ((final,),),
                    (audio_response,),
                    chat_responses=("Respuesta",),
                )
                conversation = await create_voice_conversation(service, current)
                coordinator, _ = await started(service, realtime, current, conversation, turn_id)
                with pytest.raises(MalformedVoiceEventError, match="Assistant audio"):
                    await coordinator.handle(frame(turn_id, 0))

    asyncio.run(scenario())


def test_actionable_voice_request_uses_orchestrator_and_reports_no_executor_truthfully() -> None:
    async def scenario() -> None:
        turn_id = "voice-action-turn"
        final = ProviderTranscriptEvent(
            turn_id=turn_id,
            kind=TranscriptKind.FINAL,
            text="send a notification",
        )
        plan = candidate_plan("notification.send", "send", resource_type="notification")
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = await voice_identity(session)
                await grant(session, current, "memory.read", "read", "memory")
                service, realtime = await build_voice_service(
                    session,
                    ((final,),),
                    ((audio_event(turn_id),),),
                    chat_responses=(),
                    orchestration_responses=(plan,),
                )
                conversation = await create_voice_conversation(service, current)
                coordinator, _ = await started(service, realtime, current, conversation, turn_id)
                result = await coordinator.handle(frame(turn_id, 0))
                assistant = next(
                    item for item in result if item.type is VoiceServerEventType.ASSISTANT_TEXT
                )
                assert assistant.outcome == AssistantOutcome.ACTION_WAITING_PERMISSION.value
                assert "sent" not in (assistant.text or "").casefold()

    asyncio.run(scenario())


def test_explicit_voice_memory_request_reuses_phase7_semantics() -> None:
    async def scenario() -> None:
        turn_id = "voice-memory-turn"
        final = ProviderTranscriptEvent(
            turn_id=turn_id,
            kind=TranscriptKind.FINAL,
            text="recuerda que prefiero respuestas breves",
        )
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = await voice_identity(session)
                await grant(session, current, "memory.write", "create", "memory")
                service, realtime = await build_voice_service(
                    session,
                    ((final,),),
                    ((audio_event(turn_id),),),
                    chat_responses=(),
                )
                conversation = await create_voice_conversation(service, current)
                coordinator, _ = await started(service, realtime, current, conversation, turn_id)
                result = await coordinator.handle(frame(turn_id, 0))
                assistant = next(
                    item for item in result if item.type is VoiceServerEventType.ASSISTANT_TEXT
                )
                assert assistant.outcome == AssistantOutcome.MEMORY_SAVED.value
                assert assistant.text == "Lo recordaré."

    asyncio.run(scenario())


def test_safe_mode_voice_action_fails_closed() -> None:
    async def scenario() -> None:
        turn_id = "voice-safe-mode-action"
        final = ProviderTranscriptEvent(
            turn_id=turn_id,
            kind=TranscriptKind.FINAL,
            text="send a notification",
        )
        plan = candidate_plan("notification.send", "send", resource_type="notification")
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = await voice_identity(session)
                service, realtime = await build_voice_service(
                    session,
                    ((final,),),
                    ((audio_event(turn_id),),),
                    chat_responses=(),
                    orchestration_responses=(plan,),
                    safe_mode=SafeMode.SAFE_MODE,
                )
                conversation = await create_voice_conversation(service, current)
                coordinator, _ = await started(service, realtime, current, conversation, turn_id)
                result = await coordinator.handle(frame(turn_id, 0))
                assistant = next(
                    item for item in result if item.type is VoiceServerEventType.ASSISTANT_TEXT
                )
                assert assistant.outcome == AssistantOutcome.ACTION_DENIED.value

    asyncio.run(scenario())


def test_session_owner_device_and_active_connection_are_enforced() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                owner = await voice_identity(session)
                other = await voice_identity(session)
                service, _ = await build_voice_service(session, (), ())
                conversation = await create_voice_conversation(service, owner)
                with pytest.raises(ConversationNotFoundError):
                    await service.start(
                        other,
                        VoiceSessionCreateRequest(conversation_id=conversation.id),
                    )
                response = await service.start(
                    owner,
                    VoiceSessionCreateRequest(conversation_id=conversation.id),
                )
                await service.open_connection(response.id, response.credential)
                with pytest.raises(VoiceSessionConflictError):
                    await service.open_connection(response.id, response.credential)

    asyncio.run(scenario())


def test_refresh_invalidates_old_credential_and_expired_credential_is_rejected() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = await voice_identity(session)
                service, _ = await build_voice_service(session, (), ())
                conversation = await create_voice_conversation(service, current)
                response = await service.start(
                    current,
                    VoiceSessionCreateRequest(conversation_id=conversation.id),
                )
                refreshed = await service.refresh_credential(current, response.id)
                with pytest.raises(VoiceSessionAuthFailedError):
                    await service.open_connection(response.id, response.credential)
                record = await session.get(VoiceSession, response.id)
                assert record is not None
                record.credential_expires_at = utc_now() - timedelta(seconds=1)
                await session.flush()
                with pytest.raises(VoiceSessionExpiredError):
                    await service.open_connection(response.id, refreshed.credential)

    asyncio.run(scenario())


def test_max_session_duration_expires_terminally_and_credential_ttl_is_short() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = await voice_identity(session)
                service, _ = await build_voice_service(
                    session,
                    (),
                    (),
                    policy=VoiceSessionPolicy(
                        credential_ttl_seconds=30,
                        max_session_seconds=60,
                    ),
                )
                conversation = await create_voice_conversation(service, current)
                response = await service.start(
                    current,
                    VoiceSessionCreateRequest(conversation_id=conversation.id),
                )
                assert (response.credential_expires_at - response.started_at).total_seconds() <= 30
                record = await session.get(VoiceSession, response.id)
                assert record is not None
                record.started_at = utc_now() - timedelta(seconds=61)
                await session.flush()
                with pytest.raises(VoiceSessionExpiredError):
                    await service.open_connection(response.id, response.credential)
                assert record.state is VoiceSessionState.FAILED
                assert record.ended_at is not None

    asyncio.run(scenario())


def test_reconnect_is_bounded_and_late_connection_generation_cannot_mutate() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = await voice_identity(session)
                service, _ = await build_voice_service(session, (), ())
                conversation = await create_voice_conversation(service, current)
                response = await service.start(
                    current,
                    VoiceSessionCreateRequest(conversation_id=conversation.id),
                )
                old_access = await service.open_connection(response.id, response.credential)
                await service.disconnect(old_access, end=False)
                new_access = await service.open_connection(response.id, response.credential)
                with pytest.raises(VoiceSessionAuthFailedError):
                    await service.finalize_turn(old_access, "late-turn-0001", "late", 1.0)
                await service.disconnect(new_access, end=False)
                third = await service.open_connection(response.id, response.credential)
                await service.disconnect(third, end=False)
                fourth = await service.open_connection(response.id, response.credential)
                await service.disconnect(fourth, end=False)
                with pytest.raises(VoiceReconnectExhaustedError):
                    await service.open_connection(response.id, response.credential)

    asyncio.run(scenario())
