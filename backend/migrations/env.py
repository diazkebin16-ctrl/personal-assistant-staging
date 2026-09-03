"""Alembic environment using the same async database configuration as the app."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from backend.app.ai_router import models as ai_router_models  # noqa: F401
from backend.app.audit import models as audit_models  # noqa: F401
from backend.app.core.config import Settings
from backend.app.core.database import normalize_database_url
from backend.app.identity.models import Base
from backend.app.memory import models as memory_models  # noqa: F401
from backend.app.orchestrator import models as orchestrator_models  # noqa: F401
from backend.app.permissions import models as permission_models  # noqa: F401
from backend.app.tasks import models as task_models  # noqa: F401
from backend.app.text_assistant import models as text_assistant_models  # noqa: F401
from backend.app.voice import models as voice_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    """Resolve an explicitly supplied Alembic URL or central application settings."""
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url:
        return normalize_database_url(configured_url)

    settings = Settings()
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required to run migrations")
    return normalize_database_url(settings.database_url.get_secret_value())


def run_migrations_offline() -> None:
    """Run migrations without creating an engine."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run online migrations through SQLAlchemy's async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
