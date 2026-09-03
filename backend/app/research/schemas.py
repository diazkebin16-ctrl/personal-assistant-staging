"""Strict provider-neutral contracts for search, evidence, and citations."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from backend.app.research.enums import ResearchMode

BoundedText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4096)]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    snippet: str = Field(default="", max_length=4000)
    rank: int = Field(ge=1, le=1000)


class FetchedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_url: str = Field(min_length=1, max_length=4096)
    title: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=200_000, repr=False)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(pattern=r"^ev_[0-9a-f]{16}$")
    canonical_url: str = Field(min_length=1, max_length=4096)
    title: str = Field(min_length=1, max_length=500)
    passage: str = Field(min_length=1, max_length=4000, repr=False)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    locator: str = Field(min_length=1, max_length=128)
    retrieved_at: datetime
    quality_score: int = Field(ge=0, le=100)


class ResearchCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_id: str = Field(pattern=r"^cit_[0-9a-f]{16}$")
    evidence_id: str = Field(pattern=r"^ev_[0-9a-f]{16}$")
    url: str = Field(min_length=1, max_length=4096)
    title: str = Field(min_length=1, max_length=500)
    retrieved_at: datetime
    locator: str = Field(min_length=1, max_length=128)

    @field_validator("url")
    @classmethod
    def public_web_url_only(cls, value: str) -> str:
        if not value.startswith(("https://", "http://")):
            raise ValueError("Citations require an HTTP(S) URL")
        return value


class SynthesisClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=5000)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=5)


class SynthesisEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claims: tuple[SynthesisClaim, ...] = Field(min_length=1, max_length=12)


class ResearchAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: ResearchMode
    content: str = Field(min_length=1, max_length=100_000)
    citations: tuple[ResearchCitation, ...] = Field(min_length=1, max_length=12)
    routing_decision_id: UUID | None = None
