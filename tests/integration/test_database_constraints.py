"""Runtime database constraint tests using isolated SQLite."""

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.identity.models import Device, DeviceType, User
from tests.helpers import isolated_database


def test_duplicate_auth_user_id_is_prevented() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            auth_user_id = uuid4()
            async with database.session_factory() as session:
                session.add_all(
                    [
                        User(auth_user_id=auth_user_id),
                        User(auth_user_id=auth_user_id),
                    ]
                )
                with pytest.raises(IntegrityError):
                    await session.commit()

    asyncio.run(scenario())


def test_duplicate_device_identity_for_same_user_is_prevented() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                user = User(auth_user_id=uuid4())
                session.add(user)
                await session.flush()
                common: dict[str, Any] = {
                    "user_id": user.id,
                    "device_name": "Browser",
                    "device_type": DeviceType.WEB,
                    "platform": "WEB",
                    "device_identifier": "duplicate-installation",
                    "capabilities": {},
                }
                session.add_all([Device(**common), Device(**common)])
                with pytest.raises(IntegrityError):
                    await session.commit()

    asyncio.run(scenario())


def test_device_foreign_key_is_enforced() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                session.add(
                    Device(
                        user_id=uuid4(),
                        device_name="Orphan",
                        device_type=DeviceType.UNKNOWN,
                        platform="UNKNOWN",
                        device_identifier="orphan-installation",
                        capabilities={},
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()

    asyncio.run(scenario())


def test_status_enum_and_required_auth_identity_are_enforced() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                with pytest.raises(IntegrityError):
                    await session.execute(
                        text(
                            "INSERT INTO users (id, auth_user_id, status) "
                            "VALUES (:id, :auth_user_id, :status)"
                        ),
                        {
                            "id": uuid4().hex,
                            "auth_user_id": uuid4().hex,
                            "status": "INVALID",
                        },
                    )
                    await session.commit()
                await session.rollback()

                with pytest.raises(IntegrityError):
                    await session.execute(
                        text(
                            "INSERT INTO users (id, auth_user_id, status) "
                            "VALUES (:id, NULL, 'ACTIVE')"
                        ),
                        {"id": uuid4().hex},
                    )
                    await session.commit()

    asyncio.run(scenario())
