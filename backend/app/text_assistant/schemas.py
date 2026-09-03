"""Strict public commands and controlled Text Assistant responses."""

import hashlib
import json
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.app.core.time import as_utc
from backend.app.research.schemas import ResearchCitation
from backend.app.security.classification import DataSensitivity
from backend.app.tasks.schemas import IdempotencyKey
from backend.app.text_assistant.enums import AssistantOutcome, MessageRole, MessageStatus
from backend.app.text_assistant.models import Conversation, ConversationMessage

MessageContent = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50_000)
]
ConversationTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: ConversationTitle | None = None


class MemoryTarget(BaseModel):
    """Owner-scoped reference; it grants no deletion or confirmation authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: UUID
    expected_version: int = Field(ge=1)
    confirmation_id: UUID | None = None


class AssistantRequest(BaseModel):
    """Narrow message command without owner, model, risk, or sensitivity authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: MessageContent = Field(repr=False)
    idempotency_key: IdempotencyKey
    expected_version: int = Field(ge=1)
    use_memory_context: bool = True
    memory_items_per_category: int = Field(default=3, ge=1, le=5)
    requested_output_tokens: int = Field(default=1024, ge=1, le=8192)
    memory_target: MemoryTarget | None = None
    research_confirmation_id: UUID | None = None

    def fingerprint(self, conversation_id: UUID) -> str:
        payload = {
            "content_sha256": hashlib.sha256(self.content.encode()).hexdigest(),
            "conversation_id": str(conversation_id),
            "memory_items_per_category": self.memory_items_per_category,
            "memory_target": (
                self.memory_target.model_dump(mode="json") if self.memory_target else None
            ),
            "requested_output_tokens": self.requested_output_tokens,
            "research_confirmation_id": (
                str(self.research_confirmation_id) if self.research_confirmation_id else None
            ),
            "use_memory_context": self.use_memory_context,
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        return hashlib.sha256(encoded).hexdigest()


class ConversationResponse(BaseModel):
    id: UUID
    device_id: UUID | None
    title: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None

    @classmethod
    def from_model(cls, conversation: Conversation) -> "ConversationResponse":
        return cls(
            id=conversation.id,
            device_id=conversation.device_id,
            title=conversation.title,
            version=conversation.version,
            created_at=as_utc(conversation.created_at),
            updated_at=as_utc(conversation.updated_at),
            last_message_at=(
                as_utc(conversation.last_message_at) if conversation.last_message_at else None
            ),
        )


class ConversationMessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: MessageRole
    status: MessageStatus
    outcome: AssistantOutcome | None
    sequence: int
    content: str
    sensitivity: DataSensitivity
    orchestration_id: UUID | None
    confirmation_request_id: UUID | None
    memory_id: UUID | None
    reason_code: str | None
    citations: tuple[ResearchCitation, ...] = ()
    created_at: datetime

    @classmethod
    def from_model(cls, message: ConversationMessage) -> "ConversationMessageResponse":
        return cls(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role,
            status=message.status,
            outcome=message.outcome,
            sequence=message.sequence,
            content=message.content,
            sensitivity=message.sensitivity,
            orchestration_id=message.orchestration_id,
            confirmation_request_id=message.confirmation_request_id,
            memory_id=message.memory_id,
            reason_code=message.reason_code,
            citations=tuple(
                ResearchCitation.model_validate(item) for item in message.research_citations
            ),
            created_at=as_utc(message.created_at),
        )


class AssistantResponse(BaseModel):
    """Truthful result coupled to persisted user and assistant messages."""

    conversation: ConversationResponse
    user_message: ConversationMessageResponse
    assistant_message: ConversationMessageResponse
