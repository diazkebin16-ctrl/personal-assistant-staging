"""Runtime Memory Core database-invariant tests."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app.identity.models import User
from backend.app.memory.enums import MemoryClass, MemorySourceType, MemoryStatus
from backend.app.memory.models import MemoryRecord
from backend.app.security.classification import DataSensitivity
from tests.helpers import isolated_database


def _memory(user_id: UUID, *, memory_class: MemoryClass, key: str | None) -> MemoryRecord:
    return MemoryRecord(
        user_id=user_id,
        memory_class=memory_class,
        status=MemoryStatus.ACTIVE,
        source_type=MemorySourceType.USER_EXPLICIT,
        content="Constraint test memory",
        normalized_content="Constraint test memory",
        confidence=100,
        importance=50,
        sensitivity=DataSensitivity.PRIVATE,
        fingerprint="a" * 64,
        deduplication_key=key,
        version=1,
        metadata_payload={},
    )


def test_active_deduplication_has_database_race_protection() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                user = User(auth_user_id=uuid4())
                session.add(user)
                await session.flush()
                key = "b" * 64
                session.add_all(
                    [
                        _memory(
                            user.id,
                            memory_class=MemoryClass.PERSISTENT_PREFERENCE,
                            key=key,
                        ),
                        _memory(
                            user.id,
                            memory_class=MemoryClass.PERSISTENT_PREFERENCE,
                            key=key,
                        ),
                    ]
                )
                with pytest.raises(IntegrityError):
                    await session.commit()

    asyncio.run(scenario())


def test_temporary_memory_requires_expiry_at_database_boundary() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                user = User(auth_user_id=uuid4())
                session.add(user)
                await session.flush()
                session.add(
                    _memory(user.id, memory_class=MemoryClass.TEMPORARY_CONTEXT, key="c" * 64)
                )
                with pytest.raises(IntegrityError):
                    await session.commit()

    asyncio.run(scenario())


def test_confidence_importance_and_owner_foreign_key_are_database_enforced() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                invalid = _memory(uuid4(), memory_class=MemoryClass.OPERATIONAL, key="d" * 64)
                invalid.confidence = 101
                invalid.importance = -1
                session.add(invalid)
                with pytest.raises(IntegrityError):
                    await session.commit()

    asyncio.run(scenario())
