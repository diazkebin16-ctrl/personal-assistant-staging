"""Authenticated Voice session control and scoped realtime WebSocket transport."""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.auth.dependencies import CurrentIdentity
from backend.app.core.config import Environment
from backend.app.core.errors import (
    ApplicationError,
    VoiceReconnectExhaustedError,
    VoiceSessionExpiredError,
)
from backend.app.voice.dependencies import VoiceServiceDependency
from backend.app.voice.enums import VoiceErrorCode, VoiceServerEventType
from backend.app.voice.protocol import (
    MalformedVoiceEventError,
    VoiceProtocolCoordinator,
    parse_client_event,
)
from backend.app.voice.provider import RealtimeProviderFailure
from backend.app.voice.schemas import (
    VoiceServerEvent,
    VoiceSessionCreateRequest,
    VoiceSessionCredentialResponse,
    VoiceSessionResponse,
    VoiceSessionStateResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice")


@router.post("/sessions", response_model=VoiceSessionResponse)
async def start_voice_session(
    request: VoiceSessionCreateRequest,
    identity: CurrentIdentity,
    service: VoiceServiceDependency,
) -> VoiceSessionResponse:
    return await service.start(identity, request)


@router.post(
    "/sessions/{session_id}/credential",
    response_model=VoiceSessionCredentialResponse,
)
async def refresh_voice_credential(
    session_id: UUID,
    identity: CurrentIdentity,
    service: VoiceServiceDependency,
) -> VoiceSessionCredentialResponse:
    return await service.refresh_credential(identity, session_id)


@router.post("/sessions/{session_id}/end", response_model=VoiceSessionStateResponse)
async def end_voice_session(
    session_id: UUID,
    identity: CurrentIdentity,
    service: VoiceServiceDependency,
) -> VoiceSessionStateResponse:
    state = await service.end_owned(identity, session_id)
    return VoiceSessionStateResponse(session_id=session_id, state=state)


@router.websocket("/sessions/{session_id}/stream")
async def stream_voice_session(
    websocket: WebSocket,
    session_id: UUID,
    service: VoiceServiceDependency,
) -> None:
    settings = websocket.app.state.settings
    if settings.environment is Environment.PRODUCTION and websocket.url.scheme != "wss":
        await websocket.close(code=1008)
        return
    credential = websocket.headers.get("X-Voice-Session-Token")
    if credential is None or not 32 <= len(credential) <= 256:
        await websocket.close(code=4401)
        return

    coordinator: VoiceProtocolCoordinator | None = None
    access = None
    try:
        access = await service.open_connection(session_id, credential)
        provider = service.providers.get(access.provider_key)
        connection = await asyncio.wait_for(
            provider.connect(access.model_id, access.voice_profile),
            timeout=service.policy.connection_timeout_seconds,
        )
        coordinator = VoiceProtocolCoordinator(service, access, connection)
        await service.session.commit()
        await websocket.accept()
        await _send(
            websocket,
            VoiceServerEvent(
                type=VoiceServerEventType.SESSION_STATE,
                state=await service.state_for_connection(access),
            ),
        )

        while not coordinator.ended:
            try:
                payload = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=service.policy.idle_timeout_seconds,
                )
            except TimeoutError:
                await _send(
                    websocket,
                    VoiceServerEvent(
                        type=VoiceServerEventType.ERROR,
                        error=VoiceErrorCode.SESSION_TIMEOUT,
                    ),
                )
                await connection.close()
                await service.disconnect(access, end=True)
                await service.session.commit()
                await websocket.close(code=1000)
                return
            events = await coordinator.handle(parse_client_event(payload))
            await service.session.commit()
            for event in events:
                await _send(websocket, event)
    except WebSocketDisconnect:
        if coordinator is not None and access is not None:
            await coordinator.provider.close()
            await service.disconnect(access, end=False)
            await service.session.commit()
    except MalformedVoiceEventError:
        await service.session.rollback()
        if coordinator is not None:
            events = await coordinator.fail(VoiceErrorCode.MALFORMED_EVENT)
            await service.session.commit()
            if websocket.client_state.name == "CONNECTED":
                for event in events:
                    await _send(websocket, event)
                await websocket.close(code=1003)
    except (VoiceReconnectExhaustedError, VoiceSessionExpiredError):
        await service.session.commit()
        if websocket.client_state.name == "CONNECTED":
            await websocket.close(code=4403)
    except (ApplicationError, RealtimeProviderFailure, TimeoutError):
        await service.session.rollback()
        if coordinator is not None and access is not None:
            await coordinator.provider.close()
            await service.fail_connection(access)
            await service.session.commit()
        logger.warning(
            "Voice stream rejected safely",
            extra={"voice_session_id": str(session_id)},
        )
        if websocket.client_state.name == "CONNECTED":
            await websocket.close(code=4403)
    finally:
        if coordinator is not None and not coordinator.ended:
            await coordinator.provider.close()


async def _send(websocket: WebSocket, event: VoiceServerEvent) -> None:
    await websocket.send_text(event.model_dump_json(exclude_none=True))
