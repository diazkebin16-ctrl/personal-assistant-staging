"""FastAPI dependency wiring for the Memory Core."""

from typing import Annotated

from fastapi import Depends

from backend.app.identity.dependencies import DatabaseSession
from backend.app.memory.service import MemoryService
from backend.app.permissions.dependencies import AuditEngineDependency, PermissionsEngineDependency


def get_memory_service(
    session: DatabaseSession,
    permissions: PermissionsEngineDependency,
    audit: AuditEngineDependency,
) -> MemoryService:
    return MemoryService(session, permissions, audit)


MemoryServiceDependency = Annotated[MemoryService, Depends(get_memory_service)]
