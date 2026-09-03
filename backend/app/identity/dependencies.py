"""FastAPI dependency wiring for the identity service."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db_session
from backend.app.identity.service import IdentityService

DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_identity_service(session: DatabaseSession) -> IdentityService:
    return IdentityService(session)


IdentityServiceDependency = Annotated[IdentityService, Depends(get_identity_service)]
