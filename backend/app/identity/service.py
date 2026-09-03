"""Transactional identity provisioning, session mapping, and device ownership logic."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.claims import SupabaseClaims
from backend.app.core.errors import (
    DeviceNotFoundError,
    DeviceRevokedError,
    IdentityConflictError,
    SessionRevokedError,
    UserDisabledError,
)
from backend.app.identity.context import IdentityContext
from backend.app.identity.models import AuthSession, Device, User, UserStatus, utc_now
from backend.app.identity.schemas import DeviceRegistrationRequest, safe_display_name


class IdentityService:
    """Own the Phase 1 persistence rules without implementing authorization policy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve_identity(
        self,
        claims: SupabaseClaims,
        requested_device_id: UUID | None,
    ) -> IdentityContext:
        now = utc_now()
        user = await self._get_or_create_user(claims, now)
        if user.status is UserStatus.DISABLED:
            raise UserDisabledError

        requested_device = await self._owned_device(user.id, requested_device_id)
        auth_session, effective_device = await self._map_session(
            claims,
            user,
            requested_device,
            now,
        )
        user.last_seen_at = now

        return IdentityContext(
            user_id=user.id,
            auth_user_id=user.auth_user_id,
            device_id=effective_device.id if effective_device else None,
            session_id=auth_session.id if auth_session else None,
            display_name=user.display_name,
            authentication_level=claims.authentication_level,
            token_expiry=claims.token_expiry,
        )

    async def register_device(
        self,
        identity: IdentityContext,
        registration: DeviceRegistrationRequest,
    ) -> Device:
        now = utc_now()
        device = await self.session.scalar(
            select(Device).where(
                Device.user_id == identity.user_id,
                Device.device_identifier == registration.device_identifier,
            )
        )

        if device is None:
            device = Device(
                user_id=identity.user_id,
                device_name=registration.device_name,
                device_type=registration.device_type,
                platform=registration.platform,
                device_identifier=registration.device_identifier,
                public_key=registration.public_key,
                capabilities=dict(registration.capabilities),
                last_seen_at=now,
            )
            try:
                async with self.session.begin_nested():
                    self.session.add(device)
                    await self.session.flush()
            except IntegrityError:
                device = await self.session.scalar(
                    select(Device).where(
                        Device.user_id == identity.user_id,
                        Device.device_identifier == registration.device_identifier,
                    )
                )
                if device is None:
                    raise IdentityConflictError from None

        if device.revoked_at is not None:
            raise DeviceRevokedError

        device.device_name = registration.device_name
        device.device_type = registration.device_type
        device.platform = registration.platform
        device.capabilities = dict(registration.capabilities)
        if registration.public_key is not None:
            device.public_key = registration.public_key
        device.last_seen_at = now
        device.updated_at = now

        if identity.session_id is not None:
            auth_session = await self.session.get(AuthSession, identity.session_id)
            if auth_session is None or auth_session.user_id != identity.user_id:
                raise IdentityConflictError
            if auth_session.device_id not in (None, device.id):
                raise IdentityConflictError
            auth_session.device_id = device.id
            auth_session.last_seen_at = now

        await self.session.flush()
        return device

    async def list_devices(self, identity: IdentityContext) -> list[Device]:
        devices = await self.session.scalars(
            select(Device)
            .where(Device.user_id == identity.user_id)
            .order_by(Device.created_at, Device.id)
        )
        return list(devices)

    async def revoke_device(self, identity: IdentityContext, device_id: UUID) -> Device:
        device = await self.session.scalar(
            select(Device).where(
                Device.id == device_id,
                Device.user_id == identity.user_id,
            )
        )
        if device is None:
            raise DeviceNotFoundError

        if device.revoked_at is None:
            now = utc_now()
            device.revoked_at = now
            device.updated_at = now
            await self.session.execute(
                update(AuthSession)
                .where(
                    AuthSession.device_id == device.id,
                    AuthSession.revoked_at.is_(None),
                )
                .values(revoked_at=now, updated_at=now)
            )
            await self.session.flush()
        return device

    async def _get_or_create_user(self, claims: SupabaseClaims, now: datetime) -> User:
        user = await self.session.scalar(select(User).where(User.auth_user_id == claims.sub))
        if user is not None:
            return user

        user = User(
            auth_user_id=claims.sub,
            display_name=safe_display_name(claims.user_metadata),
            status=UserStatus.ACTIVE,
            last_seen_at=now,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(user)
                await self.session.flush()
            return user
        except IntegrityError:
            existing = await self.session.scalar(
                select(User).where(User.auth_user_id == claims.sub)
            )
            if existing is None:
                raise IdentityConflictError from None
            return existing

    async def _owned_device(
        self,
        user_id: UUID,
        requested_device_id: UUID | None,
    ) -> Device | None:
        if requested_device_id is None:
            return None
        device = await self.session.scalar(
            select(Device).where(
                Device.id == requested_device_id,
                Device.user_id == user_id,
            )
        )
        if device is None:
            raise DeviceNotFoundError
        if device.revoked_at is not None:
            raise DeviceRevokedError
        return device

    async def _map_session(
        self,
        claims: SupabaseClaims,
        user: User,
        requested_device: Device | None,
        now: datetime,
    ) -> tuple[AuthSession | None, Device | None]:
        if claims.session_id is None:
            return None, requested_device

        auth_session = await self.session.scalar(
            select(AuthSession).where(AuthSession.auth_session_identifier == claims.session_id)
        )
        if auth_session is None:
            auth_session = AuthSession(
                user_id=user.id,
                device_id=requested_device.id if requested_device else None,
                auth_session_identifier=claims.session_id,
                last_seen_at=now,
                expires_at=claims.token_expiry,
            )
            try:
                async with self.session.begin_nested():
                    self.session.add(auth_session)
                    await self.session.flush()
            except IntegrityError:
                auth_session = await self.session.scalar(
                    select(AuthSession).where(
                        AuthSession.auth_session_identifier == claims.session_id
                    )
                )
                if auth_session is None:
                    raise IdentityConflictError from None

        if auth_session.user_id != user.id:
            raise IdentityConflictError
        if auth_session.revoked_at is not None:
            raise SessionRevokedError

        effective_device = requested_device
        if auth_session.device_id is not None:
            if requested_device is not None and requested_device.id != auth_session.device_id:
                raise IdentityConflictError
            effective_device = await self._owned_device(user.id, auth_session.device_id)
        elif requested_device is not None:
            auth_session.device_id = requested_device.id

        auth_session.last_seen_at = now
        auth_session.expires_at = claims.token_expiry
        return auth_session, effective_device
