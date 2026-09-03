"""Internal identity, device, and observed authentication-session models."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base."""


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class DeviceType(StrEnum):
    ANDROID = "ANDROID"
    IOS = "IOS"
    WEB = "WEB"
    DESKTOP = "DESKTOP"
    WATCH = "WATCH"
    UNKNOWN = "UNKNOWN"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )


class User(TimestampMixin, Base):
    """Internal profile mapped one-to-one to a Supabase Auth user."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("auth_user_id", name="uq_users_auth_user_id"),
        CheckConstraint(
            "display_name IS NULL OR length(display_name) BETWEEN 1 AND 100",
            name="ck_users_display_name_length",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED')",
            name="user_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    auth_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        SqlEnum(
            UserStatus,
            name="user_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    devices: Mapped[list["Device"]] = relationship(
        back_populates="user",
        passive_deletes=True,
    )
    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user",
        passive_deletes=True,
    )


class Device(TimestampMixin, Base):
    """Known installation associated with exactly one internal user."""

    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("user_id", "device_identifier", name="uq_devices_user_identifier"),
        CheckConstraint(
            "length(device_name) BETWEEN 1 AND 100",
            name="ck_devices_name_length",
        ),
        CheckConstraint(
            "length(platform) BETWEEN 1 AND 64",
            name="ck_devices_platform_length",
        ),
        CheckConstraint(
            "length(device_identifier) BETWEEN 8 AND 128",
            name="ck_devices_identifier_length",
        ),
        CheckConstraint(
            "public_key IS NULL OR length(public_key) <= 4096",
            name="ck_devices_public_key_length",
        ),
        CheckConstraint(
            "length(CAST(capabilities AS TEXT)) <= 8192",
            name="ck_devices_capabilities_size",
        ),
        CheckConstraint(
            "device_type IN ('ANDROID', 'IOS', 'WEB', 'DESKTOP', 'WATCH', 'UNKNOWN')",
            name="device_type",
        ),
        Index("ix_devices_user_last_seen", "user_id", "last_seen_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    device_name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_type: Mapped[DeviceType] = mapped_column(
        SqlEnum(
            DeviceType,
            name="device_type",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    device_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    trusted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    public_key: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    capabilities: Mapped[dict[str, bool]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="devices")
    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="device",
        passive_deletes=True,
    )


class AuthSession(TimestampMixin, Base):
    """Observed mapping to a Supabase Auth session, never a replacement for it."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        UniqueConstraint(
            "auth_session_identifier",
            name="uq_auth_sessions_identifier",
        ),
        CheckConstraint(
            "length(auth_session_identifier) BETWEEN 1 AND 255",
            name="ck_auth_sessions_identifier_length",
        ),
        Index("ix_auth_sessions_user_last_seen", "user_id", "last_seen_at"),
        Index("ix_auth_sessions_device_id", "device_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    device_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
    )
    auth_session_identifier: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")
    device: Mapped[Device | None] = relationship(back_populates="sessions")
