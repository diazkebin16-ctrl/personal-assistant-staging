"""FastAPI dependency wiring for the Task Engine service."""

from typing import Annotated

from fastapi import Depends

from backend.app.identity.dependencies import DatabaseSession
from backend.app.permissions.dependencies import AuditEngineDependency, PermissionsEngineDependency
from backend.app.tasks.service import TaskService


def get_task_service(
    session: DatabaseSession,
    permissions: PermissionsEngineDependency,
    audit: AuditEngineDependency,
) -> TaskService:
    return TaskService(session, permissions, audit)


TaskServiceDependency = Annotated[TaskService, Depends(get_task_service)]
