"""Validated immutable identity context passed to later application layers."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuthenticationLevel(StrEnum):
    AAL1 = "AAL1"
    AAL2 = "AAL2"
    UNKNOWN = "UNKNOWN"


class IdentityContext(BaseModel):
    """Verified request identity; it intentionally carries no permissions."""

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    auth_user_id: UUID
    device_id: UUID | None
    session_id: UUID | None
    display_name: str | None
    authentication_level: AuthenticationLevel
    token_expiry: datetime
    authenticated: Literal[True] = True
