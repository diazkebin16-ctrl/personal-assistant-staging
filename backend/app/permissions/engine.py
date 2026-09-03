"""Default-deny authority pipeline with independent risk and safety guards."""

import logging
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.audit.engine import AuditEngine
from backend.app.audit.schemas import AuditRecord
from backend.app.core.time import at_or_after
from backend.app.identity.context import IdentityContext
from backend.app.identity.models import Device, User, UserStatus, utc_now
from backend.app.permissions.enums import (
    ActorType,
    AuditEventType,
    AuditResult,
    AuthorizationDecisionType,
    ConfirmationPolicy,
    ConfirmationStatus,
    DecisionReason,
    PermissionStatus,
    RiskLevel,
)
from backend.app.permissions.financial import FinancialExecutionGuard
from backend.app.permissions.models import (
    AuthorizationDecisionRecord,
    Capability,
    ConfirmationRequest,
    Permission,
)
from backend.app.permissions.risk import RiskEngine
from backend.app.permissions.schemas import (
    AuthorizationDecision,
    AuthorizationRequest,
    PermissionScope,
    RiskAssessment,
)

logger = logging.getLogger(__name__)
CONFIRMATION_TTL = timedelta(minutes=5)


class PermissionsEngine:
    """Evaluate authority in one documented order and never perform side effects."""

    def __init__(
        self,
        session: AsyncSession,
        audit: AuditEngine,
        risk_engine: RiskEngine | None = None,
        financial_guard: FinancialExecutionGuard | None = None,
    ) -> None:
        self.session = session
        self.audit = audit
        self.risk_engine = risk_engine or RiskEngine()
        self.financial_guard = financial_guard or FinancialExecutionGuard()

    async def authorize(
        self, identity: IdentityContext, request: AuthorizationRequest
    ) -> AuthorizationDecision:
        """Identity -> capability -> permission -> risk -> guard -> confirmation -> audit."""
        user = await self.session.get(User, identity.user_id)
        if user is None or user.auth_user_id != identity.auth_user_id:
            return await self._finalize(
                identity,
                request,
                AuthorizationDecisionType.DENY,
                (DecisionReason.INVALID_IDENTITY,),
                None,
                RiskLevel.NEGLIGIBLE,
                False,
                False,
            )
        if user.status is UserStatus.DISABLED:
            return await self._finalize(
                identity,
                request,
                AuthorizationDecisionType.DENY,
                (DecisionReason.USER_DISABLED,),
                None,
                RiskLevel.NEGLIGIBLE,
                False,
                False,
            )

        capability = await self.session.scalar(
            select(Capability).where(Capability.key == request.capability_key)
        )
        if capability is None:
            return await self._finalize(
                identity,
                request,
                AuthorizationDecisionType.DENY,
                (DecisionReason.CAPABILITY_NOT_FOUND,),
                None,
                RiskLevel.NEGLIGIBLE,
                False,
                False,
            )
        if not capability.enabled:
            return await self._finalize(
                identity,
                request,
                AuthorizationDecisionType.DENY,
                (DecisionReason.CAPABILITY_DISABLED,),
                None,
                RiskLevel(capability.default_risk_level),
                False,
                False,
            )
        if not capability.allows_operations(request.scope.operations):
            return await self._finalize(
                identity,
                request,
                AuthorizationDecisionType.DENY,
                (DecisionReason.ACTION_NOT_ALLOWED,),
                None,
                RiskLevel(capability.default_risk_level),
                False,
                False,
            )

        permission, failure_reason, scope_match = await self._find_permission(
            identity, capability, request.scope
        )
        if permission is None:
            return await self._finalize(
                identity,
                request,
                AuthorizationDecisionType.DENY,
                (failure_reason,),
                None,
                RiskLevel(capability.default_risk_level),
                scope_match,
                False,
            )

        try:
            risk = self.risk_engine.evaluate(
                capability=capability,
                action=request.action,
                scope=request.scope,
                identity=identity,
                context=request.context,
            )
            financial_blocked = self.financial_guard.blocks(capability)
        except Exception:  # Safety classifier failures are authority failures, never ALLOW.
            logger.exception("Risk or safety evaluation failed")
            return await self._finalize(
                identity,
                request,
                AuthorizationDecisionType.DENY,
                (DecisionReason.AUTHORIZATION_EVALUATION_FAILED,),
                permission,
                RiskLevel.CRITICAL,
                True,
                False,
            )

        if financial_blocked:
            decision = await self._finalize(
                identity,
                request,
                AuthorizationDecisionType.DENY,
                (DecisionReason.FINANCIAL_EXECUTION_BLOCKED,),
                permission,
                RiskLevel.CRITICAL,
                True,
                True,
            )
            await self.audit.record(
                self._audit_record(
                    identity=identity,
                    request=request,
                    event_type=AuditEventType.FINANCIAL_GUARD_TRIGGERED,
                    result=AuditResult.DENIED,
                    decision_id=decision.decision_id,
                    permission_id=permission.id,
                    risk_level=RiskLevel.CRITICAL,
                    reason_codes=(DecisionReason.FINANCIAL_EXECUTION_BLOCKED.value,),
                )
            )
            return decision

        confirmation_result = await self._confirmation_result(identity, request, permission, risk)
        if confirmation_result is not None:
            decision_type, reasons = confirmation_result
            return await self._finalize(
                identity, request, decision_type, reasons, permission, risk.risk_level, True, False
            )

        permission.last_used_at = utc_now()
        permission.updated_at = permission.last_used_at
        return await self._finalize(
            identity,
            request,
            AuthorizationDecisionType.ALLOW,
            (DecisionReason.AUTHORIZED,),
            permission,
            risk.risk_level,
            True,
            False,
        )

    async def capability_allows(self, capability_key: str, action: str) -> bool:
        """Read the server-owned Capability action vocabulary without granting authority."""
        capability = await self.session.scalar(
            select(Capability).where(Capability.key == capability_key, Capability.enabled.is_(True))
        )
        return capability is not None and capability.allows_operations((action,))

    async def get_owned_decision(
        self, identity: IdentityContext, decision_id: UUID
    ) -> AuthorizationDecision | None:
        """Expose immutable evidence without coordinator table access."""
        record = await self.session.scalar(
            select(AuthorizationDecisionRecord).where(
                AuthorizationDecisionRecord.id == decision_id,
                AuthorizationDecisionRecord.user_id == identity.user_id,
            )
        )
        if record is None:
            return None
        confirmation = await self.session.scalar(
            select(ConfirmationRequest).where(
                ConfirmationRequest.authorization_decision_id == record.id
            )
        )
        return AuthorizationDecision(
            decision_id=record.id,
            decision=record.decision,
            reason_codes=tuple(DecisionReason(code) for code in record.reason_codes),
            permission_id=record.permission_id,
            risk_level=RiskLevel(record.risk_level),
            confirmation_required=record.confirmation_required,
            confirmation_id=confirmation.id if confirmation else None,
            scope_match=record.scope_match,
            financial_guard_triggered=record.financial_guard_triggered,
            created_at=record.created_at,
        )

    async def _find_permission(
        self,
        identity: IdentityContext,
        capability: Capability,
        requested_scope: PermissionScope,
    ) -> tuple[Permission | None, DecisionReason, bool]:
        permissions = list(
            await self.session.scalars(
                select(Permission)
                .where(
                    Permission.user_id == identity.user_id,
                    Permission.capability_id == capability.id,
                )
                .order_by(Permission.granted_at.desc(), Permission.id)
            )
        )
        if not permissions:
            return None, DecisionReason.NO_PERMISSION, False

        now = utc_now()
        saw_revoked = False
        saw_expired = False
        saw_scope_match = False
        saw_invalid_action = False
        device_reason = DecisionReason.DEVICE_SCOPE_MISMATCH

        for permission in permissions:
            if permission.status is PermissionStatus.REVOKED:
                saw_revoked = True
                continue
            if permission.status is PermissionStatus.EXPIRED or (
                permission.expires_at is not None and at_or_after(now, permission.expires_at)
            ):
                saw_expired = True
                if permission.status is PermissionStatus.ACTIVE:
                    permission.status = PermissionStatus.EXPIRED
                    permission.updated_at = now
                    await self.audit.record(
                        self._audit_record(
                            identity=identity,
                            request=None,
                            event_type=AuditEventType.PERMISSION_EXPIRED_OBSERVED,
                            result=AuditResult.RECORDED,
                            decision_id=None,
                            permission_id=permission.id,
                            risk_level=None,
                            capability_key=capability.key,
                            reason_codes=(DecisionReason.PERMISSION_EXPIRED.value,),
                        )
                    )
                continue

            granted_scope = PermissionScope.model_validate(permission.scope)
            if not capability.allows_operations(granted_scope.operations):
                saw_invalid_action = True
                continue
            if not granted_scope.authorizes(requested_scope):
                continue
            saw_scope_match = True

            if permission.device_id is not None:
                if identity.device_id != permission.device_id:
                    continue
                device = await self.session.get(Device, permission.device_id)
                if device is None or device.user_id != identity.user_id:
                    continue
                if device.revoked_at is not None:
                    device_reason = DecisionReason.DEVICE_REVOKED
                    continue
            return permission, DecisionReason.AUTHORIZED, True

        if saw_scope_match:
            return None, device_reason, True
        if saw_invalid_action:
            return None, DecisionReason.ACTION_NOT_ALLOWED, False
        if saw_expired:
            return None, DecisionReason.PERMISSION_EXPIRED, False
        if saw_revoked:
            return None, DecisionReason.PERMISSION_REVOKED, False
        return None, DecisionReason.SCOPE_MISMATCH, False

    async def _confirmation_result(
        self,
        identity: IdentityContext,
        request: AuthorizationRequest,
        permission: Permission,
        risk: RiskAssessment,
    ) -> tuple[AuthorizationDecisionType, tuple[DecisionReason, ...]] | None:
        policy_requires = (
            permission.confirmation_policy is ConfirmationPolicy.EVERY_TIME
            or (
                permission.confirmation_policy is ConfirmationPolicy.ONCE
                and permission.confirmed_once_at is None
            )
            or (
                permission.confirmation_policy is ConfirmationPolicy.HIGH_RISK_ONLY
                and risk.risk_level >= RiskLevel.HIGH
            )
        )
        if not policy_requires:
            return None

        if request.confirmation_id is None:
            return (
                AuthorizationDecisionType.REQUIRE_CONFIRMATION,
                (DecisionReason.CONFIRMATION_REQUIRED,),
            )

        confirmation = await self.session.scalar(
            select(ConfirmationRequest).where(
                ConfirmationRequest.id == request.confirmation_id,
                ConfirmationRequest.user_id == identity.user_id,
            )
        )
        if confirmation is None or (
            confirmation.permission_id != permission.id
            or confirmation.capability_key != request.capability_key
            or confirmation.action != request.action
            or confirmation.scope_digest != request.scope.digest
        ):
            return AuthorizationDecisionType.DENY, (DecisionReason.CONFIRMATION_MISMATCH,)

        now = utc_now()
        if at_or_after(now, confirmation.expires_at) or (
            confirmation.status is ConfirmationStatus.EXPIRED
        ):
            confirmation.status = ConfirmationStatus.EXPIRED
            return AuthorizationDecisionType.DENY, (DecisionReason.CONFIRMATION_EXPIRED,)
        if confirmation.status is ConfirmationStatus.REJECTED:
            return AuthorizationDecisionType.DENY, (DecisionReason.CONFIRMATION_REJECTED,)
        if confirmation.status is not ConfirmationStatus.APPROVED:
            return (
                AuthorizationDecisionType.REQUIRE_CONFIRMATION,
                (DecisionReason.CONFIRMATION_REQUIRED,),
            )
        if confirmation.consumed_at is not None:
            return AuthorizationDecisionType.DENY, (DecisionReason.CONFIRMATION_REPLAYED,)

        confirmation.consumed_at = now
        return None

    async def _finalize(
        self,
        identity: IdentityContext,
        request: AuthorizationRequest,
        decision_type: AuthorizationDecisionType,
        reasons: tuple[DecisionReason, ...],
        permission: Permission | None,
        risk_level: RiskLevel,
        scope_match: bool,
        financial_guard_triggered: bool,
    ) -> AuthorizationDecision:
        now = utc_now()
        decision_id = uuid4()
        confirmation_required = decision_type is AuthorizationDecisionType.REQUIRE_CONFIRMATION
        record = AuthorizationDecisionRecord(
            id=decision_id,
            user_id=identity.user_id,
            device_id=identity.device_id,
            permission_id=permission.id if permission else None,
            capability_key=request.capability_key,
            action=request.action,
            scope=request.scope.model_dump(mode="json"),
            scope_digest=request.scope.digest,
            decision=decision_type,
            reason_codes=[reason.value for reason in reasons],
            risk_level=int(risk_level),
            confirmation_required=confirmation_required,
            scope_match=scope_match,
            financial_guard_triggered=financial_guard_triggered,
            created_at=now,
        )
        self.session.add(record)
        await self.session.flush()

        confirmation: ConfirmationRequest | None = None
        if confirmation_required:
            if permission is None:
                raise RuntimeError("Confirmation cannot be created without a permission")
            confirmation = ConfirmationRequest(
                user_id=identity.user_id,
                authorization_decision_id=decision_id,
                permission_id=permission.id,
                capability_key=request.capability_key,
                action=request.action,
                scope_digest=request.scope.digest,
                status=ConfirmationStatus.PENDING,
                requested_at=now,
                expires_at=now + CONFIRMATION_TTL,
            )
            self.session.add(confirmation)
            await self.session.flush()

        event_type = {
            AuthorizationDecisionType.ALLOW: AuditEventType.AUTHORIZATION_ALLOWED,
            AuthorizationDecisionType.DENY: AuditEventType.AUTHORIZATION_DENIED,
            AuthorizationDecisionType.REQUIRE_CONFIRMATION: AuditEventType.CONFIRMATION_REQUESTED,
        }[decision_type]
        result = {
            AuthorizationDecisionType.ALLOW: AuditResult.ALLOWED,
            AuthorizationDecisionType.DENY: AuditResult.DENIED,
            AuthorizationDecisionType.REQUIRE_CONFIRMATION: AuditResult.REQUESTED,
        }[decision_type]
        await self.audit.record(
            self._audit_record(
                identity=identity,
                request=request,
                event_type=event_type,
                result=result,
                decision_id=decision_id,
                permission_id=permission.id if permission else None,
                confirmation_id=confirmation.id if confirmation else None,
                risk_level=risk_level,
                reason_codes=tuple(reason.value for reason in reasons),
            )
        )
        await self.session.flush()

        logger.info(
            "Authorization evaluated",
            extra={
                "user_id": str(identity.user_id),
                "device_id": str(identity.device_id) if identity.device_id else None,
                "capability_key": request.capability_key,
                "risk_level": int(risk_level),
                "decision_id": str(decision_id),
            },
        )
        return AuthorizationDecision(
            decision_id=decision_id,
            decision=decision_type,
            reason_codes=reasons,
            permission_id=permission.id if permission else None,
            risk_level=risk_level,
            confirmation_required=confirmation_required,
            confirmation_id=confirmation.id if confirmation else None,
            scope_match=scope_match,
            financial_guard_triggered=financial_guard_triggered,
            created_at=now,
        )

    def _audit_record(
        self,
        *,
        identity: IdentityContext,
        request: AuthorizationRequest | None,
        event_type: AuditEventType,
        result: AuditResult,
        decision_id: UUID | None,
        permission_id: UUID | None,
        risk_level: RiskLevel | None,
        reason_codes: tuple[str, ...],
        capability_key: str | None = None,
        confirmation_id: UUID | None = None,
    ) -> AuditRecord:
        resource_type = request.scope.resource_type if request else None
        resource_id = (
            request.resource.resource_id if request and request.resource is not None else None
        )
        return AuditRecord(
            user_id=identity.user_id,
            device_id=identity.device_id,
            session_id=identity.session_id,
            actor_type=ActorType.USER,
            event_type=event_type,
            result=result,
            capability_key=(request.capability_key if request else capability_key),
            action=request.action if request else None,
            resource_type=resource_type,
            resource_id=resource_id,
            risk_level=risk_level,
            permission_id=permission_id,
            authorization_decision_id=decision_id,
            confirmation_id=confirmation_id,
            reason_codes=reason_codes,
        )
