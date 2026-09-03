"""Transactional VoiceSession authority bridging final speech into Text Assistant."""

import hashlib
import hmac
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai_router.enums import Complexity, ModelCapability, RoutingOutcome
from backend.app.ai_router.schemas import RoutingRequest
from backend.app.ai_router.service import AIRouter
from backend.app.core.errors import (
    AIRoutingDeniedError,
    CapabilityDisabledError,
    DeviceNotFoundError,
    DeviceRevokedError,
    InvalidVoiceTransitionApplicationError,
    RealtimeModelUnavailableError,
    SessionRevokedError,
    UserDisabledError,
    VoiceReconnectExhaustedError,
    VoiceSessionAuthFailedError,
    VoiceSessionConflictError,
    VoiceSessionExpiredError,
    VoiceSessionNotFoundError,
    VoiceTurnIdempotencyConflictError,
)
from backend.app.core.time import as_utc
from backend.app.identity.context import AuthenticationLevel, IdentityContext
from backend.app.identity.models import AuthSession, Device, User, UserStatus, utc_now
from backend.app.security.classification import DataSensitivity
from backend.app.text_assistant.models import Conversation
from backend.app.text_assistant.schemas import AssistantRequest
from backend.app.text_assistant.service import TextAssistantService
from backend.app.voice.enums import VoiceSessionState, VoiceTurnStatus
from backend.app.voice.models import VoiceSession, VoiceTurn
from backend.app.voice.observability import NullVoiceObserver, VoiceMetricEvent, VoiceObserver
from backend.app.voice.provider import RealtimeProviderFailure, RealtimeProviderRegistry
from backend.app.voice.schemas import (
    MAX_RECONNECT_ATTEMPTS,
    VoiceSessionAccess,
    VoiceSessionCreateRequest,
    VoiceSessionCredentialResponse,
    VoiceSessionResponse,
    VoiceTurnResult,
)
from backend.app.voice.state_machine import InvalidVoiceTransitionError, require_voice_transition

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VoiceSessionPolicy:
    credential_ttl_seconds: int = 120
    connection_timeout_seconds: int = 10
    idle_timeout_seconds: int = 45
    max_session_seconds: int = 900
    max_reconnect_attempts: int = MAX_RECONNECT_ATTEMPTS
    voice_profile: str = "calm-professional-v1"

    def __post_init__(self) -> None:
        if not 30 <= self.credential_ttl_seconds <= 300:
            raise ValueError("Voice credential TTL must remain short")
        if not 5 <= self.connection_timeout_seconds <= 30:
            raise ValueError("Voice connection timeout is out of bounds")
        if not 15 <= self.idle_timeout_seconds <= 300:
            raise ValueError("Voice idle timeout is out of bounds")
        if not 60 <= self.max_session_seconds <= 3600:
            raise ValueError("Voice maximum session duration is out of bounds")
        if not 0 <= self.max_reconnect_attempts <= MAX_RECONNECT_ATTEMPTS:
            raise ValueError("Voice reconnect attempts exceed the certified bound")
        if re.fullmatch(r"[a-z][a-z0-9-]{1,63}", self.voice_profile) is None:
            raise ValueError("Voice profile identifier is invalid")


class VoiceSessionService:
    """One server-side session path; partial transcripts never enter authority domains."""

    def __init__(
        self,
        session: AsyncSession,
        text_assistant: TextAssistantService,
        ai_router: AIRouter,
        providers: RealtimeProviderRegistry,
        *,
        policy: VoiceSessionPolicy | None = None,
        observer: VoiceObserver | None = None,
    ) -> None:
        self.session = session
        self.text_assistant = text_assistant
        self.ai_router = ai_router
        self.providers = providers
        self.policy = policy or VoiceSessionPolicy()
        self.observer = observer or NullVoiceObserver()

    async def start(
        self,
        identity: IdentityContext,
        request: VoiceSessionCreateRequest,
    ) -> VoiceSessionResponse:
        if identity.device_id is None:
            raise DeviceNotFoundError
        if identity.session_id is None:
            raise VoiceSessionAuthFailedError
        device = await self._owned_active_device(identity.user_id, identity.device_id)
        if device.capabilities.get("microphone") is not True:
            raise CapabilityDisabledError
        conversation = await self.text_assistant.get_owned(identity, request.conversation_id)

        # Raw speech is semantically unknown before STT. Treat the ingress as CRITICAL so
        # an external provider can never receive content that has not yet been classified.
        routing_request = RoutingRequest(
            task_type="voice.realtime_session",
            complexity=Complexity.HIGH,
            required_capabilities=frozenset(
                {ModelCapability.AUDIO_REALTIME, ModelCapability.TEXT_GENERATION}
            ),
            sensitivity=DataSensitivity.CRITICAL,
            estimated_input_tokens=1,
            requested_output_tokens=4096,
            realtime_required=True,
            local_only=True,
        )
        try:
            decision = await self.ai_router.route(identity, routing_request)
        except AIRoutingDeniedError:
            raise RealtimeModelUnavailableError from None
        if decision.outcome is not RoutingOutcome.SELECTED or decision.selected_model is None:
            raise RealtimeModelUnavailableError
        selected = decision.selected_model
        try:
            self.providers.get(selected.provider_key)
        except RealtimeProviderFailure:
            raise RealtimeModelUnavailableError from None

        token = self._new_credential()
        now = utc_now()
        credential_expiry = min(
            now + timedelta(seconds=self.policy.credential_ttl_seconds),
            as_utc(identity.token_expiry),
        )
        if credential_expiry <= now:
            raise VoiceSessionAuthFailedError
        record = VoiceSession(
            user_id=identity.user_id,
            device_id=device.id,
            auth_session_id=identity.session_id,
            conversation_id=conversation.id,
            state=VoiceSessionState.CONNECTING,
            authentication_level=identity.authentication_level,
            credential_hash=self._credential_hash(token),
            credential_expires_at=credential_expiry,
            routing_decision_id=decision.id,
            provider_key=selected.provider_key,
            model_id=selected.model_id,
            voice_profile=self.policy.voice_profile,
            effective_sensitivity=DataSensitivity.CRITICAL,
            started_at=now,
            last_activity_at=now,
            created_at=now,
            updated_at=now,
        )
        self.session.add(record)
        await self.session.flush()
        self._metric("voice.session.started", record)
        logger.info(
            "Voice session created",
            extra={
                "voice_session_id": str(record.id),
                "conversation_id": str(record.conversation_id),
                "device_id": str(record.device_id),
            },
        )
        return VoiceSessionResponse.from_model(
            record,
            token,
            idle_timeout_seconds=self.policy.idle_timeout_seconds,
            max_session_seconds=self.policy.max_session_seconds,
        )

    async def refresh_credential(
        self, identity: IdentityContext, session_id: UUID
    ) -> VoiceSessionCredentialResponse:
        record = await self._owned(identity, session_id, lock=True)
        if identity.device_id != record.device_id or identity.session_id != record.auth_session_id:
            raise VoiceSessionAuthFailedError
        self._require_not_terminal_or_timed_out(record)
        token = self._new_credential()
        now = utc_now()
        expiry = min(
            now + timedelta(seconds=self.policy.credential_ttl_seconds),
            as_utc(identity.token_expiry),
        )
        if expiry <= now:
            raise VoiceSessionAuthFailedError
        record.credential_hash = self._credential_hash(token)
        record.credential_expires_at = expiry
        record.updated_at = now
        record.version += 1
        await self.session.flush()
        return VoiceSessionCredentialResponse(
            session_id=record.id,
            credential=token,
            credential_expires_at=as_utc(expiry),
        )

    async def open_connection(self, session_id: UUID, credential: str) -> VoiceSessionAccess:
        record = await self._get(session_id, lock=True)
        now = utc_now()
        if not hmac.compare_digest(record.credential_hash, self._credential_hash(credential)):
            raise VoiceSessionAuthFailedError
        if as_utc(record.credential_expires_at) <= now:
            raise VoiceSessionExpiredError
        await self._identity_for(record)
        self._require_not_terminal_or_timed_out(record)

        if record.connection_id is not None:
            idle_at = as_utc(record.last_activity_at) + timedelta(
                seconds=self.policy.idle_timeout_seconds
            )
            if idle_at > now:
                raise VoiceSessionConflictError
            record.connection_id = None
            record.disconnected_at = now
            self._transition(record, VoiceSessionState.RECONNECTING)

        reconnecting = record.connected_at is not None
        if reconnecting:
            if record.reconnect_count >= self.policy.max_reconnect_attempts:
                self._transition(record, VoiceSessionState.FAILED)
                record.ended_at = now
                raise VoiceReconnectExhaustedError
            record.reconnect_count += 1
            if record.state is not VoiceSessionState.RECONNECTING:
                self._transition(record, VoiceSessionState.RECONNECTING)

        if record.state is VoiceSessionState.RECONNECTING:
            self._transition(record, VoiceSessionState.CONNECTING)
        self._transition(record, VoiceSessionState.LISTENING)
        connection_id = uuid4()
        record.connection_id = connection_id
        record.connected_at = now
        record.disconnected_at = None
        record.last_activity_at = now
        record.updated_at = now
        record.version += 1
        await self.session.flush()
        self._metric("voice.session.connected", record)
        return VoiceSessionAccess(
            session_id=record.id,
            connection_id=connection_id,
            user_id=record.user_id,
            device_id=record.device_id,
            conversation_id=record.conversation_id,
            provider_key=record.provider_key,
            model_id=record.model_id,
            voice_profile=record.voice_profile,
        )

    async def identity_for_connection(self, access: VoiceSessionAccess) -> IdentityContext:
        record = await self._require_connection(access, lock=False)
        return await self._identity_for(record)

    async def state_for_connection(self, access: VoiceSessionAccess) -> VoiceSessionState:
        return (await self._require_connection(access, lock=False)).state

    async def finalize_turn(
        self,
        access: VoiceSessionAccess,
        turn_id: str,
        transcript: str,
        confidence: float | None,
    ) -> VoiceTurnResult:
        record = await self._require_connection(access, lock=True)
        identity = await self._identity_for(record)
        fingerprint = hashlib.sha256(transcript.encode()).hexdigest()
        idempotency_key = self._turn_idempotency(record.id, turn_id)
        existing = await self.session.scalar(
            select(VoiceTurn).where(
                VoiceTurn.session_id == record.id,
                VoiceTurn.logical_turn_id == turn_id,
            )
        )
        if existing is not None and existing.transcript_sha256 != fingerprint:
            raise VoiceTurnIdempotencyConflictError
        replayed = existing is not None and existing.status is VoiceTurnStatus.COMPLETED

        conversation = await self.session.scalar(
            select(Conversation).where(
                Conversation.id == record.conversation_id,
                Conversation.user_id == record.user_id,
            )
        )
        if conversation is None:
            raise VoiceSessionNotFoundError

        if existing is None:
            self._transition(record, VoiceSessionState.PROCESSING)
            existing = VoiceTurn(
                session_id=record.id,
                user_id=record.user_id,
                conversation_id=record.conversation_id,
                logical_turn_id=turn_id,
                idempotency_key=idempotency_key,
                transcript_sha256=fingerprint,
                confidence=round(confidence * 10_000) if confidence is not None else None,
                status=VoiceTurnStatus.PROCESSING,
            )
            self.session.add(existing)
            await self.session.flush()

        response = await self.text_assistant.submit(
            identity,
            record.conversation_id,
            AssistantRequest(
                content=transcript,
                idempotency_key=idempotency_key,
                expected_version=conversation.version,
            ),
        )
        now = utc_now()
        existing.user_message_id = response.user_message.id
        existing.assistant_message_id = response.assistant_message.id
        existing.status = VoiceTurnStatus.COMPLETED
        existing.completed_at = now
        if record.state is VoiceSessionState.PROCESSING:
            self._transition(record, VoiceSessionState.SPEAKING)
        record.last_activity_at = now
        record.updated_at = now
        record.version += 1
        await self.session.flush()
        self._metric("voice.turn.completed", record, turn_id=turn_id)
        return VoiceTurnResult(turn_id=turn_id, response=response, replayed=replayed)

    async def interrupt(self, access: VoiceSessionAccess, turn_id: str) -> VoiceSessionState:
        record = await self._require_connection(access, lock=True)
        if record.state is VoiceSessionState.SPEAKING:
            self._transition(record, VoiceSessionState.INTERRUPTING)
            self._transition(record, VoiceSessionState.LISTENING)
        elif record.state is VoiceSessionState.PROCESSING:
            self._transition(record, VoiceSessionState.LISTENING)
        elif record.state is not VoiceSessionState.LISTENING:
            raise InvalidVoiceTransitionApplicationError
        record.last_activity_at = utc_now()
        record.updated_at = record.last_activity_at
        record.version += 1
        turn = await self.session.scalar(
            select(VoiceTurn).where(
                VoiceTurn.session_id == record.id,
                VoiceTurn.logical_turn_id == turn_id,
                VoiceTurn.status == VoiceTurnStatus.PROCESSING,
            )
        )
        if turn is not None:
            turn.status = VoiceTurnStatus.INTERRUPTED
            turn.interrupted_at = record.last_activity_at
        await self.session.flush()
        self._metric("voice.turn.interrupted", record, turn_id=turn_id)
        return record.state

    async def playback_completed(
        self, access: VoiceSessionAccess, turn_id: str
    ) -> VoiceSessionState:
        del turn_id
        record = await self._require_connection(access, lock=True)
        if record.state is VoiceSessionState.SPEAKING:
            self._transition(record, VoiceSessionState.LISTENING)
        elif record.state is not VoiceSessionState.LISTENING:
            raise InvalidVoiceTransitionApplicationError
        record.last_activity_at = utc_now()
        record.updated_at = record.last_activity_at
        record.version += 1
        await self.session.flush()
        return record.state

    async def disconnect(self, access: VoiceSessionAccess, *, end: bool = False) -> None:
        record = await self.session.scalar(
            select(VoiceSession)
            .where(
                VoiceSession.id == access.session_id,
                VoiceSession.connection_id == access.connection_id,
            )
            .with_for_update()
        )
        if record is None:
            return
        now = utc_now()
        record.connection_id = None
        record.disconnected_at = now
        record.last_activity_at = now
        record.updated_at = now
        record.version += 1
        if record.state not in {VoiceSessionState.ENDED, VoiceSessionState.FAILED}:
            self._transition(
                record, VoiceSessionState.ENDED if end else VoiceSessionState.RECONNECTING
            )
            if end:
                record.ended_at = now
        await self.session.flush()
        self._metric("voice.session.disconnected", record)

    async def fail_connection(self, access: VoiceSessionAccess) -> None:
        record = await self.session.scalar(
            select(VoiceSession)
            .where(
                VoiceSession.id == access.session_id,
                VoiceSession.connection_id == access.connection_id,
            )
            .with_for_update()
        )
        if record is None:
            return
        now = utc_now()
        record.connection_id = None
        record.disconnected_at = now
        record.last_activity_at = now
        record.updated_at = now
        record.version += 1
        if record.state not in {VoiceSessionState.ENDED, VoiceSessionState.FAILED}:
            self._transition(record, VoiceSessionState.FAILED)
            record.ended_at = now
        await self.session.flush()
        self._metric("voice.session.failed", record)

    async def end_owned(self, identity: IdentityContext, session_id: UUID) -> VoiceSessionState:
        record = await self._owned(identity, session_id, lock=True)
        if record.state not in {VoiceSessionState.ENDED, VoiceSessionState.FAILED}:
            self._transition(record, VoiceSessionState.ENDED)
            now = utc_now()
            record.connection_id = None
            record.ended_at = now
            record.updated_at = now
            record.version += 1
            await self.session.flush()
        return record.state

    async def _owned(
        self, identity: IdentityContext, session_id: UUID, *, lock: bool
    ) -> VoiceSession:
        statement: Select[tuple[VoiceSession]] = select(VoiceSession).where(
            VoiceSession.id == session_id,
            VoiceSession.user_id == identity.user_id,
        )
        if lock:
            statement = statement.with_for_update()
        record = await self.session.scalar(statement)
        if record is None:
            raise VoiceSessionNotFoundError
        return record

    async def _get(self, session_id: UUID, *, lock: bool) -> VoiceSession:
        statement: Select[tuple[VoiceSession]] = select(VoiceSession).where(
            VoiceSession.id == session_id
        )
        if lock:
            statement = statement.with_for_update()
        record = await self.session.scalar(statement)
        if record is None:
            raise VoiceSessionAuthFailedError
        return record

    async def _require_connection(self, access: VoiceSessionAccess, *, lock: bool) -> VoiceSession:
        statement: Select[tuple[VoiceSession]] = select(VoiceSession).where(
            VoiceSession.id == access.session_id,
            VoiceSession.connection_id == access.connection_id,
            VoiceSession.user_id == access.user_id,
            VoiceSession.device_id == access.device_id,
            VoiceSession.conversation_id == access.conversation_id,
        )
        if lock:
            statement = statement.with_for_update()
        record = await self.session.scalar(statement)
        if record is None:
            raise VoiceSessionAuthFailedError
        self._require_not_terminal_or_timed_out(record)
        return record

    async def _owned_active_device(self, user_id: UUID, device_id: UUID) -> Device:
        device = await self.session.scalar(
            select(Device).where(Device.id == device_id, Device.user_id == user_id)
        )
        if device is None:
            raise DeviceNotFoundError
        if device.revoked_at is not None:
            raise DeviceRevokedError
        return device

    async def _identity_for(self, record: VoiceSession) -> IdentityContext:
        user = await self.session.get(User, record.user_id)
        auth_session = await self.session.get(AuthSession, record.auth_session_id)
        device = await self._owned_active_device(record.user_id, record.device_id)
        now = utc_now()
        if user is None or user.status is UserStatus.DISABLED:
            raise UserDisabledError
        if (
            auth_session is None
            or auth_session.user_id != user.id
            or auth_session.device_id != device.id
            or auth_session.revoked_at is not None
            or as_utc(auth_session.expires_at) <= now
        ):
            raise SessionRevokedError
        return IdentityContext(
            user_id=user.id,
            auth_user_id=user.auth_user_id,
            device_id=device.id,
            session_id=auth_session.id,
            display_name=user.display_name,
            authentication_level=AuthenticationLevel(record.authentication_level),
            token_expiry=as_utc(auth_session.expires_at),
        )

    def _require_not_terminal_or_timed_out(self, record: VoiceSession) -> None:
        if record.state in {VoiceSessionState.ENDED, VoiceSessionState.FAILED}:
            raise VoiceSessionExpiredError
        now = utc_now()
        if as_utc(record.started_at) + timedelta(seconds=self.policy.max_session_seconds) <= now:
            self._transition(record, VoiceSessionState.FAILED)
            record.ended_at = now
            raise VoiceSessionExpiredError

    @staticmethod
    def _transition(record: VoiceSession, target: VoiceSessionState) -> None:
        try:
            record.state = require_voice_transition(record.state, target)
        except InvalidVoiceTransitionError:
            raise InvalidVoiceTransitionApplicationError from None

    @staticmethod
    def _new_credential() -> str:
        return secrets.token_urlsafe(48)

    @staticmethod
    def _credential_hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _turn_idempotency(session_id: UUID, turn_id: str) -> str:
        digest = hashlib.sha256(f"{session_id}:{turn_id}".encode()).hexdigest()
        return f"voice:{digest}"

    def _metric(self, name: str, record: VoiceSession, *, turn_id: str | None = None) -> None:
        attributes: dict[str, str | int | bool] = {
            "voice_session_id": str(record.id),
            "conversation_id": str(record.conversation_id),
            "state": record.state.value,
            "reconnect_count": record.reconnect_count,
        }
        if turn_id is not None:
            attributes["turn_id"] = turn_id
        self.observer.emit(VoiceMetricEvent(name=name, attributes=attributes))
