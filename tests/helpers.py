"""Reusable, production-safe test fixtures based on dependency overrides."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import FastAPI
from httpx import ASGITransport
from httpx import AsyncClient as HttpxAsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai_router import models as ai_router_models  # noqa: F401
from backend.app.auth.claims import SupabaseClaims
from backend.app.auth.jwt import TokenVerifier, get_token_verifier
from backend.app.core.config import Environment, Settings
from backend.app.core.database import Database, create_database, get_db_session
from backend.app.core.errors import InvalidTokenError
from backend.app.identity.models import Base
from backend.app.main import create_app
from backend.app.permissions.enums import RiskLevel
from backend.app.permissions.models import Capability
from backend.app.text_assistant import models as text_assistant_models  # noqa: F401


class FakeTokenVerifier(TokenVerifier):
    """Explicit test-only verifier injected through FastAPI dependency overrides."""

    def __init__(self, claims_by_token: dict[str, SupabaseClaims]) -> None:
        self.claims_by_token = claims_by_token

    def verify(self, token: str) -> SupabaseClaims:
        claims = self.claims_by_token.get(token)
        if claims is None:
            raise InvalidTokenError
        return claims


def make_claims(
    *,
    auth_user_id: UUID | None = None,
    session_id: str | None = None,
    expires_delta: timedelta = timedelta(hours=1),
    aal: str | None = "aal1",
    display_name: str | None = "Test User",
) -> SupabaseClaims:
    metadata = {"display_name": display_name} if display_name else {}
    return SupabaseClaims(
        sub=auth_user_id or uuid4(),
        iss="https://test.supabase.co/auth/v1",
        aud="authenticated",
        exp=int((datetime.now(UTC) + expires_delta).timestamp()),
        role="authenticated",
        session_id=session_id,
        aal=aal,
        user_metadata=metadata,
    )


@asynccontextmanager
async def isolated_database() -> AsyncIterator[Database]:
    """Create an in-memory database; create_all is intentionally test-only."""
    database = create_database("sqlite+aiosqlite:///:memory:")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with database.session_factory() as session:
        await seed_capabilities(session)
        await session.commit()
    try:
        yield database
    finally:
        await database.engine.dispose()


@asynccontextmanager
async def api_client(
    claims_by_token: dict[str, SupabaseClaims],
) -> AsyncIterator[tuple[HttpxAsyncClient, Database, FastAPI]]:
    async with isolated_database() as database:
        application = create_app(Settings(environment=Environment.LOCAL, app_version="0.7.0"))
        verifier = FakeTokenVerifier(claims_by_token)

        async def override_session() -> AsyncIterator[AsyncSession]:
            async with database.session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        application.dependency_overrides[get_db_session] = override_session
        application.dependency_overrides[get_token_verifier] = lambda: verifier

        transport = ASGITransport(app=application)
        async with application.router.lifespan_context(application):
            async with HttpxAsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                yield client, database, application


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def seed_capabilities(session: AsyncSession) -> None:
    """Install the deterministic Phase 2 test catalog used by the migration."""
    catalog = (
        (
            "device.read",
            "Read devices",
            "Read owned device metadata",
            "device",
            1,
            ["read"],
            False,
            False,
            False,
            True,
        ),
        (
            "device.manage",
            "Manage devices",
            "Manage owned devices",
            "device",
            2,
            ["register", "revoke", "update"],
            False,
            False,
            True,
            True,
        ),
        (
            "notification.send",
            "Send notification",
            "Propose an external notification",
            "communication",
            3,
            ["send"],
            True,
            False,
            False,
            True,
        ),
        (
            "data.delete",
            "Delete data",
            "Delete owned application data",
            "data",
            4,
            ["delete"],
            False,
            False,
            True,
            True,
        ),
        (
            "finance.read",
            "Read finance",
            "Read authorized financial information",
            "finance",
            2,
            ["read"],
            False,
            True,
            False,
            True,
        ),
        (
            "finance.execute",
            "Execute finance",
            "Financial execution boundary",
            "finance",
            5,
            [
                "buy",
                "cancel_order",
                "change_leverage",
                "deposit",
                "execute",
                "increase_risk",
                "place_order",
                "sell",
                "transfer",
                "withdraw",
            ],
            True,
            True,
            False,
            True,
        ),
        (
            "memory.read",
            "Read memory",
            "Read owner-scoped active or historical memory",
            "memory",
            2,
            ["read"],
            False,
            False,
            False,
            True,
        ),
        (
            "memory.write",
            "Write memory",
            "Create, update, or archive owner-scoped memory",
            "memory",
            3,
            ["archive", "create", "update"],
            False,
            False,
            False,
            True,
        ),
        (
            "memory.delete",
            "Delete memory",
            "Privacy-delete owner-scoped memory",
            "memory",
            4,
            ["delete"],
            False,
            False,
            True,
            True,
        ),
        (
            "web.research",
            "Web research",
            "Search and retrieve bounded public web evidence",
            "research",
            1,
            ["search", "fetch", "multi_source"],
            False,
            False,
            False,
            True,
        ),
    )
    for (
        key,
        name,
        description,
        category,
        risk,
        allowed_actions,
        external,
        financial,
        destructive,
        privacy,
    ) in catalog:
        session.add(
            Capability(
                key=key,
                name=name,
                description=description,
                category=category,
                default_risk_level=RiskLevel(risk),
                allowed_actions=allowed_actions,
                external_side_effect=external,
                financial=financial,
                data_destructive=destructive,
                privacy_impact=privacy,
                enabled=True,
            )
        )
    await session.flush()
