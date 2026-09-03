"""Persistence models for capabilities, permissions, decisions, and confirmations."""

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.identity.models import Base, TimestampMixin, utc_now
from backend.app.permissions.enums import (
    AuthorizationDecisionType,
    ConfirmationPolicy,
    ConfirmationStatus,
    PermissionGrantSource,
    PermissionStatus,
)


class Capability(TimestampMixin, Base):
    """Stable server-owned description of an authorizable capability."""

    __tablename__ = "capabilities"
    __table_args__ = (
        UniqueConstraint("key", name="uq_capabilities_key"),
        CheckConstraint("length(key) BETWEEN 3 AND 128", name="ck_capabilities_key_length"),
        CheckConstraint("length(name) BETWEEN 1 AND 100", name="ck_capabilities_name_length"),
        CheckConstraint(
            "length(description) BETWEEN 1 AND 500",
            name="ck_capabilities_description_length",
        ),
        CheckConstraint(
            "length(category) BETWEEN 1 AND 64",
            name="ck_capabilities_category_length",
        ),
        CheckConstraint(
            "default_risk_level BETWEEN 0 AND 5",
            name="ck_capabilities_risk_level",
        ),
        CheckConstraint(
            "length(CAST(allowed_actions AS TEXT)) <= 4096",
            name="ck_capabilities_allowed_actions_size",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    default_risk_level: Mapped[int] = mapped_column(Integer, nullable=False)
    allowed_actions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    external_side_effect: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    financial: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    data_destructive: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    privacy_impact: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    def allows_operations(self, operations: Iterable[str]) -> bool:
        """Fail closed unless every operation belongs to the server-owned vocabulary."""
        actions: object = self.allowed_actions
        if (
            not isinstance(actions, list)
            or not actions
            or any(not isinstance(action, str) or not action for action in actions)
        ):
            return False
        return set(operations).issubset(actions)


class Permission(TimestampMixin, Base):
    """Explicit user capability grant bound to a validated scope."""

    __tablename__ = "permissions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'REVOKED', 'EXPIRED')",
            name="permission_status",
        ),
        CheckConstraint(
            "confirmation_policy IN ('NEVER', 'ONCE', 'EVERY_TIME', 'HIGH_RISK_ONLY')",
            name="confirmation_policy",
        ),
        CheckConstraint(
            "grant_source IN ('USER_EXPLICIT', 'SYSTEM_DEFAULT', 'MIGRATION')",
            name="permission_grant_source",
        ),
        CheckConstraint("length(scope_digest) = 64", name="ck_permissions_scope_digest"),
        CheckConstraint("length(CAST(scope AS TEXT)) <= 8192", name="ck_permissions_scope_size"),
        CheckConstraint(
            "reason IS NULL OR length(reason) BETWEEN 1 AND 500",
            name="ck_permissions_reason_length",
        ),
        Index(
            "ix_permissions_user_capability_status",
            "user_id",
            "capability_id",
            "status",
        ),
        Index("ix_permissions_device_id", "device_id"),
        Index("ix_permissions_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    capability_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("capabilities.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("devices.id", ondelete="RESTRICT"), nullable=True
    )
    scope: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    scope_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[PermissionStatus] = mapped_column(
        SqlEnum(
            PermissionStatus,
            name="permission_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        default=PermissionStatus.ACTIVE,
        server_default=PermissionStatus.ACTIVE.value,
        nullable=False,
    )
    confirmation_policy: Mapped[ConfirmationPolicy] = mapped_column(
        SqlEnum(
            ConfirmationPolicy,
            name="confirmation_policy",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        nullable=False,
    )
    auto_execute: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    grant_source: Mapped[PermissionGrantSource] = mapped_column(
        SqlEnum(
            PermissionGrantSource,
            name="permission_grant_source",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        nullable=False,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_once_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AuthorizationDecisionRecord(Base):
    """Immutable database snapshot used to bind human confirmation to one decision."""

    __tablename__ = "authorization_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('ALLOW', 'DENY', 'REQUIRE_CONFIRMATION')",
            name="authorization_decision",
        ),
        CheckConstraint("risk_level BETWEEN 0 AND 5", name="ck_decisions_risk_level"),
        CheckConstraint("length(scope_digest) = 64", name="ck_decisions_scope_digest"),
        CheckConstraint("length(CAST(scope AS TEXT)) <= 8192", name="ck_decisions_scope_size"),
        CheckConstraint(
            "length(CAST(reason_codes AS TEXT)) <= 4096",
            name="ck_decisions_reason_codes_size",
        ),
        Index("ix_decisions_user_created", "user_id", "created_at"),
        Index("ix_decisions_permission_id", "permission_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    permission_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("permissions.id", ondelete="SET NULL"), nullable=True
    )
    capability_key: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    scope_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[AuthorizationDecisionType] = mapped_column(
        SqlEnum(
            AuthorizationDecisionType,
            name="authorization_decision",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        nullable=False,
    )
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    risk_level: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmation_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scope_match: Mapped[bool] = mapped_column(Boolean, nullable=False)
    financial_guard_triggered: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class ConfirmationRequest(Base):
    """Human confirmation bound to one authorization decision and action fingerprint."""

    __tablename__ = "confirmation_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')",
            name="confirmation_status",
        ),
        CheckConstraint("length(scope_digest) = 64", name="ck_confirmations_scope_digest"),
        CheckConstraint("expires_at > requested_at", name="ck_confirmations_expiry"),
        UniqueConstraint(
            "authorization_decision_id",
            name="uq_confirmations_authorization_decision",
        ),
        Index("ix_confirmations_user_status", "user_id", "status"),
        Index("ix_confirmations_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    authorization_decision_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("authorization_decisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    permission_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("permissions.id", ondelete="RESTRICT"), nullable=False
    )
    capability_key: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ConfirmationStatus] = mapped_column(
        SqlEnum(
            ConfirmationStatus,
            name="confirmation_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        default=ConfirmationStatus.PENDING,
        server_default=ConfirmationStatus.PENDING.value,
        nullable=False,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
