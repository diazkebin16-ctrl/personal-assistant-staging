"""Validated Memory Core commands, queries, and controlled responses."""

import hashlib
import json
import unicodedata
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from backend.app.core.metadata import sanitize_metadata
from backend.app.core.time import as_utc
from backend.app.memory.enums import MemoryClass, MemorySourceType, MemoryStatus
from backend.app.memory.models import MemoryRecord, MemoryRevision
from backend.app.security.classification import DataSensitivity

MemoryContent = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=16_000),
]
MemorySummary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000),
]
MemorySubject = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
SourceReference = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$",
    ),
]

MAX_MEMORY_METADATA_BYTES = 4096


def normalize_memory_text(value: str) -> str:
    """Create stable Unicode/whitespace form without changing stored user wording."""
    return " ".join(unicodedata.normalize("NFKC", value).split())


def memory_fingerprint(memory_class: MemoryClass, content: str, subject: str | None) -> str:
    """Hash exact canonical semantics; it is not semantic-similarity deduplication."""
    payload = {
        "content": normalize_memory_text(content).casefold(),
        "memory_class": memory_class.value,
        "subject": normalize_memory_text(subject).casefold() if subject else None,
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _metadata(value: dict[str, object]) -> dict[str, object]:
    return sanitize_metadata(value, max_bytes=MAX_MEMORY_METADATA_BYTES)


class MemoryCreateRequest(BaseModel):
    """Public explicit-memory command with no ownership or inferred-source authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_class: MemoryClass
    content: MemoryContent
    summary: MemorySummary | None = None
    subject: MemorySubject | None = None
    source_type: Literal[MemorySourceType.USER_EXPLICIT] = MemorySourceType.USER_EXPLICIT
    source_reference: SourceReference | None = None
    source_device_id: UUID | None = None
    importance: int = Field(default=50, ge=0, le=100)
    sensitivity: DataSensitivity = DataSensitivity.PRIVATE
    expires_at: datetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    confirmation_id: UUID | None = None

    @field_validator("expires_at")
    @classmethod
    def normalize_expiry(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Memory expiry must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, object]) -> dict[str, object]:
        return _metadata(value)

    @model_validator(mode="after")
    def validate_class_expiration(self) -> "MemoryCreateRequest":
        if self.memory_class is MemoryClass.TEMPORARY_CONTEXT and self.expires_at is None:
            raise ValueError("Temporary context requires expiration")
        return self


class MemoryProposal(BaseModel):
    """Internal proposal contract; it is not a public persistence authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_class: MemoryClass
    content: MemoryContent
    summary: MemorySummary | None = None
    subject: MemorySubject | None = None
    source_type: MemorySourceType
    source_reference: SourceReference | None = None
    source_device_id: UUID | None = None
    confidence: int = Field(ge=0, le=100)
    importance: int = Field(default=50, ge=0, le=100)
    sensitivity: DataSensitivity = DataSensitivity.PRIVATE
    expires_at: datetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    confirmation_id: UUID | None = None

    @field_validator("expires_at")
    @classmethod
    def normalize_expiry(cls, value: datetime | None) -> datetime | None:
        return MemoryCreateRequest.normalize_expiry(value)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, object]) -> dict[str, object]:
        return _metadata(value)

    @model_validator(mode="after")
    def validate_source_contract(self) -> "MemoryProposal":
        if self.memory_class is MemoryClass.TEMPORARY_CONTEXT and self.expires_at is None:
            raise ValueError("Temporary context requires expiration")
        if self.source_type is MemorySourceType.DEVICE and self.source_device_id is None:
            raise ValueError("Device provenance requires a source device")
        if self.source_type in {MemorySourceType.TASK, MemorySourceType.IMPORT} and (
            self.source_reference is None
        ):
            raise ValueError("This provenance requires a source reference")
        return self


class MemoryUpdateRequest(BaseModel):
    """Explicit optimistic mutation; protected provenance and state are absent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)
    content: MemoryContent | None = None
    summary: MemorySummary | None = None
    subject: MemorySubject | None = None
    importance: int | None = Field(default=None, ge=0, le=100)
    sensitivity: DataSensitivity | None = None
    expires_at: datetime | None = None
    metadata: dict[str, object] | None = None
    confirmation_id: UUID | None = None

    @field_validator("expires_at")
    @classmethod
    def normalize_expiry(cls, value: datetime | None) -> datetime | None:
        return MemoryCreateRequest.normalize_expiry(value)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        return _metadata(value) if value is not None else None

    @model_validator(mode="after")
    def require_mutation(self) -> "MemoryUpdateRequest":
        mutable_fields = {
            "content",
            "summary",
            "subject",
            "importance",
            "sensitivity",
            "expires_at",
            "metadata",
        }
        if not (self.model_fields_set & mutable_fields):
            raise ValueError("At least one mutable memory field is required")
        if "content" in self.model_fields_set and self.content is None:
            raise ValueError("Memory content cannot be null")
        if "importance" in self.model_fields_set and self.importance is None:
            raise ValueError("Memory importance cannot be null")
        if "sensitivity" in self.model_fields_set and self.sensitivity is None:
            raise ValueError("Memory sensitivity cannot be null")
        return self


class MemoryArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)
    confirmation_id: UUID | None = None


class MemoryResponse(BaseModel):
    id: UUID
    source_device_id: UUID | None
    memory_class: MemoryClass
    content: str
    summary: str | None
    subject: str | None
    source_type: MemorySourceType
    source_reference: str | None
    confidence: int
    importance: int
    sensitivity: DataSensitivity
    status: MemoryStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    archived_at: datetime | None
    version: int
    metadata: dict[str, object]

    @classmethod
    def from_model(cls, memory: MemoryRecord) -> "MemoryResponse":
        return cls(
            id=memory.id,
            source_device_id=memory.source_device_id,
            memory_class=memory.memory_class,
            content=memory.content,
            summary=memory.summary,
            subject=memory.subject,
            source_type=memory.source_type,
            source_reference=memory.source_reference,
            confidence=memory.confidence,
            importance=memory.importance,
            sensitivity=memory.sensitivity,
            status=memory.status,
            created_at=as_utc(memory.created_at),
            updated_at=as_utc(memory.updated_at),
            expires_at=as_utc(memory.expires_at) if memory.expires_at else None,
            archived_at=as_utc(memory.archived_at) if memory.archived_at else None,
            version=memory.version,
            metadata=memory.metadata_payload,
        )


class MemoryRevisionResponse(BaseModel):
    revision_number: int
    content: str
    summary: str | None
    subject: str | None
    confidence: int
    importance: int
    sensitivity: DataSensitivity
    recorded_at: datetime

    @classmethod
    def from_model(cls, revision: MemoryRevision) -> "MemoryRevisionResponse":
        return cls(
            revision_number=revision.revision_number,
            content=revision.content,
            summary=revision.summary,
            subject=revision.subject,
            confidence=revision.confidence,
            importance=revision.importance,
            sensitivity=revision.sensitivity,
            recorded_at=as_utc(revision.recorded_at),
        )


class MemoryContextItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    memory_class: MemoryClass
    source_type: MemorySourceType
    source_reference: str | None
    subject: str | None
    text: str
    importance: int
    sensitivity: DataSensitivity
    updated_at: datetime


class MemoryContextPack(BaseModel):
    """Bounded deterministic context; no unrestricted database controls are exposed."""

    model_config = ConfigDict(frozen=True)

    persistent_preferences: tuple[MemoryContextItem, ...]
    operational_context: tuple[MemoryContextItem, ...]
    historical_decisions: tuple[MemoryContextItem, ...]
    temporary_context: tuple[MemoryContextItem, ...]
