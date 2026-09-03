"""Dependency wiring for the Phase 2 authority modules."""

from typing import Annotated

from fastapi import Depends

from backend.app.audit.engine import AuditEngine
from backend.app.identity.dependencies import DatabaseSession
from backend.app.permissions.engine import PermissionsEngine
from backend.app.permissions.service import PermissionAdministrationService


def get_audit_engine(session: DatabaseSession) -> AuditEngine:
    return AuditEngine(session)


AuditEngineDependency = Annotated[AuditEngine, Depends(get_audit_engine)]


def get_permissions_engine(
    session: DatabaseSession,
    audit: AuditEngineDependency,
) -> PermissionsEngine:
    return PermissionsEngine(session, audit)


PermissionsEngineDependency = Annotated[PermissionsEngine, Depends(get_permissions_engine)]


def get_permission_administration_service(
    session: DatabaseSession,
    audit: AuditEngineDependency,
) -> PermissionAdministrationService:
    return PermissionAdministrationService(session, audit)


PermissionAdministrationDependency = Annotated[
    PermissionAdministrationService,
    Depends(get_permission_administration_service),
]
