"""Strict account-control administration for a user's own permissions."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.audit.engine import AuditEngine
from backend.app.audit.schemas import AuditRecord
from backend.app.core.errors import (
    ActionNotAllowedError,
    CapabilityDisabledError,
    CapabilityNotFoundError,
    ConfirmationExpiredError,
    ConfirmationNotFoundError,
    ConfirmationRejectedError,
    DeviceNotFoundError,
    DeviceRevokedError,
    InvalidPermissionDataError,
    PermissionNotFoundError,
    StepUpAuthenticationRequiredError,
)
from backend.app.core.time import at_or_after
from backend.app.identity.context import AuthenticationLevel, IdentityContext
from backend.app.identity.models import Device, utc_now
from backend.app.permissions.enums import (
    ActorType,
    AuditEventType,
    AuditResult,
    ConfirmationPolicy,
    ConfirmationStatus,
    PermissionGrantSource,
    PermissionStatus,
)
from backend.app.permissions.models import Capability, ConfirmationRequest, Permission
from backend.app.permissions.schemas import PermissionGrantRequest


class PermissionAdministrationService:
    """Bootstrap boundary: AAL2 users manage only records owned by themselves."""

    def __init__(self, session: AsyncSession, audit: AuditEngine) -> None:
        self.session = session
        self.audit = audit

    async def grant(
        self,
        identity: IdentityContext,
        request: PermissionGrantRequest,
    ) -> tuple[Permission, Capability]:
        self._require_aal2(identity)
        now = utc_now()
        if request.expires_at is not None and request.expires_at <= now:
            raise InvalidPermissionDataError

        capability = await self.session.scalar(
            select(Capability).where(Capability.key == request.capability_key)
        )
        if capability is None:
            raise CapabilityNotFoundError
        if not capability.enabled:
            raise CapabilityDisabledError
        if not capability.allows_operations(request.scope.operations):
            raise ActionNotAllowedError

        if request.device_id is not None:
            await self._require_owned_active_device(identity.user_id, request.device_id)

        existing = await self.session.scalar(
            select(Permission).where(
                Permission.user_id == identity.user_id,
                Permission.capability_id == capability.id,
                Permission.device_id == request.device_id,
                Permission.scope_digest == request.scope.digest,
                Permission.status == PermissionStatus.ACTIVE,
                Permission.confirmation_policy == request.confirmation_policy,
                Permission.auto_execute == request.auto_execute,
            )
        )
        if existing is not None and not self._is_expired(existing, now):
            return existing, capability
        if existing is not None:
            await self._observe_expiry(identity, existing, capability, now)

        permission = Permission(
            user_id=identity.user_id,
            capability_id=capability.id,
            device_id=request.device_id,
            scope=request.scope.model_dump(mode="json"),
            scope_digest=request.scope.digest,
            status=PermissionStatus.ACTIVE,
            confirmation_policy=request.confirmation_policy,
            auto_execute=request.auto_execute,
            grant_source=PermissionGrantSource.USER_EXPLICIT,
            granted_at=now,
            expires_at=request.expires_at,
            reason=request.reason,
        )
        self.session.add(permission)
        await self.session.flush()
        await self.audit.record(
            AuditRecord(
                user_id=identity.user_id,
                device_id=identity.device_id,
                session_id=identity.session_id,
                actor_type=ActorType.USER,
                event_type=AuditEventType.PERMISSION_GRANTED,
                result=AuditResult.RECORDED,
                capability_key=capability.key,
                permission_id=permission.id,
                reason_codes=(PermissionGrantSource.USER_EXPLICIT.value,),
                metadata={"scope_digest": permission.scope_digest},
            )
        )
        return permission, capability

    async def list_owned(self, identity: IdentityContext) -> list[tuple[Permission, Capability]]:
        rows = await self.session.execute(
            select(Permission, Capability)
            .join(Capability, Capability.id == Permission.capability_id)
            .where(Permission.user_id == identity.user_id)
            .order_by(Permission.created_at.desc(), Permission.id)
        )
        result = list(rows.tuples())
        now = utc_now()
        for permission, capability in result:
            if self._is_expired(permission, now):
                await self._observe_expiry(identity, permission, capability, now)
        return result

    async def get_owned(
        self, identity: IdentityContext, permission_id: UUID
    ) -> tuple[Permission, Capability]:
        row = (
            await self.session.execute(
                select(Permission, Capability)
                .join(Capability, Capability.id == Permission.capability_id)
                .where(
                    Permission.id == permission_id,
                    Permission.user_id == identity.user_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise PermissionNotFoundError
        permission, capability = row
        now = utc_now()
        if self._is_expired(permission, now):
            await self._observe_expiry(identity, permission, capability, now)
        return permission, capability

    async def revoke(
        self, identity: IdentityContext, permission_id: UUID
    ) -> tuple[Permission, Capability]:
        permission, capability = await self.get_owned(identity, permission_id)
        if permission.status is not PermissionStatus.REVOKED:
            now = utc_now()
            permission.status = PermissionStatus.REVOKED
            permission.revoked_at = now
            permission.updated_at = now
            await self.session.flush()
            await self.audit.record(
                AuditRecord(
                    user_id=identity.user_id,
                    device_id=identity.device_id,
                    session_id=identity.session_id,
                    actor_type=ActorType.USER,
                    event_type=AuditEventType.PERMISSION_REVOKED,
                    result=AuditResult.RECORDED,
                    capability_key=capability.key,
                    permission_id=permission.id,
                    reason_codes=(PermissionStatus.REVOKED.value,),
                )
            )
        return permission, capability

    async def approve_confirmation(
        self, identity: IdentityContext, confirmation_id: UUID
    ) -> ConfirmationRequest:
        self._require_aal2(identity)
        confirmation = await self._owned_confirmation(identity.user_id, confirmation_id)
        now = utc_now()
        if at_or_after(now, confirmation.expires_at):
            confirmation.status = ConfirmationStatus.EXPIRED
            raise ConfirmationExpiredError
        if confirmation.status is ConfirmationStatus.REJECTED:
            raise ConfirmationRejectedError
        if confirmation.status is ConfirmationStatus.EXPIRED:
            raise ConfirmationExpiredError
        if confirmation.status is ConfirmationStatus.PENDING:
            confirmation.status = ConfirmationStatus.APPROVED
            confirmation.confirmed_at = now
            permission = await self.session.get(Permission, confirmation.permission_id)
            if permission is None or permission.user_id != identity.user_id:
                raise PermissionNotFoundError
            if permission.confirmation_policy is ConfirmationPolicy.ONCE:
                permission.confirmed_once_at = now
                permission.updated_at = now
            await self.session.flush()
            await self.audit.record(
                AuditRecord(
                    user_id=identity.user_id,
                    device_id=identity.device_id,
                    session_id=identity.session_id,
                    actor_type=ActorType.USER,
                    event_type=AuditEventType.CONFIRMATION_APPROVED,
                    result=AuditResult.APPROVED,
                    capability_key=confirmation.capability_key,
                    action=confirmation.action,
                    permission_id=confirmation.permission_id,
                    authorization_decision_id=confirmation.authorization_decision_id,
                    confirmation_id=confirmation.id,
                )
            )
        return confirmation

    async def reject_confirmation(
        self, identity: IdentityContext, confirmation_id: UUID
    ) -> ConfirmationRequest:
        self._require_aal2(identity)
        confirmation = await self._owned_confirmation(identity.user_id, confirmation_id)
        now = utc_now()
        if at_or_after(now, confirmation.expires_at):
            confirmation.status = ConfirmationStatus.EXPIRED
            raise ConfirmationExpiredError
        if confirmation.status is ConfirmationStatus.APPROVED:
            raise ConfirmationRejectedError
        if confirmation.status is ConfirmationStatus.PENDING:
            confirmation.status = ConfirmationStatus.REJECTED
            confirmation.rejected_at = now
            await self.session.flush()
            await self.audit.record(
                AuditRecord(
                    user_id=identity.user_id,
                    device_id=identity.device_id,
                    session_id=identity.session_id,
                    actor_type=ActorType.USER,
                    event_type=AuditEventType.CONFIRMATION_REJECTED,
                    result=AuditResult.REJECTED,
                    capability_key=confirmation.capability_key,
                    action=confirmation.action,
                    permission_id=confirmation.permission_id,
                    authorization_decision_id=confirmation.authorization_decision_id,
                    confirmation_id=confirmation.id,
                )
            )
        return confirmation

    @staticmethod
    def _require_aal2(identity: IdentityContext) -> None:
        if identity.authentication_level is not AuthenticationLevel.AAL2:
            raise StepUpAuthenticationRequiredError

    async def _require_owned_active_device(self, user_id: UUID, device_id: UUID) -> Device:
        device = await self.session.scalar(
            select(Device).where(Device.id == device_id, Device.user_id == user_id)
        )
        if device is None:
            raise DeviceNotFoundError
        if device.revoked_at is not None:
            raise DeviceRevokedError
        return device

    async def _owned_confirmation(
        self, user_id: UUID, confirmation_id: UUID
    ) -> ConfirmationRequest:
        confirmation = await self.session.scalar(
            select(ConfirmationRequest).where(
                ConfirmationRequest.id == confirmation_id,
                ConfirmationRequest.user_id == user_id,
            )
        )
        if confirmation is None:
            raise ConfirmationNotFoundError
        return confirmation

    @staticmethod
    def _is_expired(permission: Permission, now: datetime) -> bool:
        return (
            permission.status is PermissionStatus.ACTIVE
            and permission.expires_at is not None
            and at_or_after(now, permission.expires_at)
        )

    async def _observe_expiry(
        self,
        identity: IdentityContext,
        permission: Permission,
        capability: Capability,
        now: datetime,
    ) -> None:
        permission.status = PermissionStatus.EXPIRED
        permission.updated_at = now
        await self.session.flush()
        await self.audit.record(
            AuditRecord(
                user_id=identity.user_id,
                device_id=identity.device_id,
                session_id=identity.session_id,
                actor_type=ActorType.SYSTEM,
                event_type=AuditEventType.PERMISSION_EXPIRED_OBSERVED,
                result=AuditResult.RECORDED,
                capability_key=capability.key,
                permission_id=permission.id,
                reason_codes=(PermissionStatus.EXPIRED.value,),
            )
        )
