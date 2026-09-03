"""Validated claims accepted from a signature-verified Supabase JWT."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.identity.context import AuthenticationLevel


class SupabaseClaims(BaseModel):
    """Minimum trusted Supabase Auth access-token claims."""

    model_config = ConfigDict(frozen=True, extra="allow")

    sub: UUID
    iss: str
    aud: str | list[str]
    exp: int
    role: Literal["authenticated"]
    session_id: str | None = Field(default=None, min_length=1, max_length=255)
    aal: str | None = Field(default=None, max_length=16)
    user_metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def authentication_level(self) -> AuthenticationLevel:
        if self.aal == "aal1":
            return AuthenticationLevel.AAL1
        if self.aal == "aal2":
            return AuthenticationLevel.AAL2
        return AuthenticationLevel.UNKNOWN

    @property
    def token_expiry(self) -> datetime:
        return datetime.fromtimestamp(self.exp, tz=UTC)
