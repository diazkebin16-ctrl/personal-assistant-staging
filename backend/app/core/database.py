"""Lazy SQLAlchemy 2.x database engine and FastAPI session dependency."""

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from backend.app.core.config import get_settings
from backend.app.core.errors import ApplicationError, DatabaseUnavailableError


class Database:
    """Database resources created without opening a connection."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )


def normalize_database_url(database_url: str) -> str:
    """Normalize common PostgreSQL URLs for the asyncpg SQLAlchemy dialect."""
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_database(database_url: str) -> Database:
    """Create lazy engine resources suitable for production or isolated tests."""
    normalized_url = normalize_database_url(database_url)
    engine_options: dict[str, Any] = {"pool_pre_ping": True}

    if normalized_url.startswith("sqlite+aiosqlite://"):
        engine_options.update({"poolclass": StaticPool})
    else:
        engine_options.update(
            {
                "pool_size": 5,
                "max_overflow": 10,
                "pool_recycle": 1800,
            }
        )

    engine = create_async_engine(normalized_url, **engine_options)
    if normalized_url.startswith("sqlite+aiosqlite://"):
        event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    return Database(engine)


@lru_cache(maxsize=1)
def get_database() -> Database:
    """Create database resources only when an endpoint needs persistence."""
    settings = get_settings()
    if settings.database_url is None:
        raise DatabaseUnavailableError
    return create_database(settings.database_url.get_secret_value())


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield one transactional session and hide database internals on failure."""
    database = get_database()
    async with database.session_factory() as session:
        try:
            yield session
            await session.commit()
        except ApplicationError:
            await session.rollback()
            raise
        except SQLAlchemyError:
            await session.rollback()
            raise DatabaseUnavailableError from None
