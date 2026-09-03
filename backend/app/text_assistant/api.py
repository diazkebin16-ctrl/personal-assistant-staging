"""Narrow authenticated Text Assistant API; no raw completion or execution proxy."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from backend.app.auth.dependencies import CurrentIdentity
from backend.app.text_assistant.dependencies import TextAssistantDependency
from backend.app.text_assistant.schemas import (
    AssistantRequest,
    AssistantResponse,
    ConversationCreateRequest,
    ConversationMessageResponse,
    ConversationResponse,
)

router = APIRouter()


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    request: ConversationCreateRequest,
    identity: CurrentIdentity,
    service: TextAssistantDependency,
) -> ConversationResponse:
    return ConversationResponse.from_model(await service.create_conversation(identity, request))


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    identity: CurrentIdentity,
    service: TextAssistantDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> list[ConversationResponse]:
    records = await service.list_owned(identity, limit=limit, offset=offset)
    return [ConversationResponse.from_model(item) for item in records]


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    identity: CurrentIdentity,
    service: TextAssistantDependency,
) -> ConversationResponse:
    return ConversationResponse.from_model(await service.get_owned(identity, conversation_id))


@router.post("/conversations/{conversation_id}/messages", response_model=AssistantResponse)
async def submit_message(
    conversation_id: UUID,
    request: AssistantRequest,
    identity: CurrentIdentity,
    service: TextAssistantDependency,
) -> AssistantResponse:
    return await service.submit(identity, conversation_id, request)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[ConversationMessageResponse],
)
async def list_messages(
    conversation_id: UUID,
    identity: CurrentIdentity,
    service: TextAssistantDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> list[ConversationMessageResponse]:
    records = await service.list_messages(identity, conversation_id, limit=limit, offset=offset)
    return [ConversationMessageResponse.from_model(item) for item in records]
