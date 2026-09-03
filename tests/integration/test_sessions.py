"""Observed Supabase session mapping tests."""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import func, select

from backend.app.identity.models import AuthSession
from tests.helpers import api_client, bearer, make_claims


def test_session_mapping_is_idempotent_and_preserves_expiry() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="mapped-session")
        async with api_client({"user-a": claims}) as (client, database, _):
            first = await client.get("/api/v1/me", headers=bearer("user-a"))
            second = await client.get("/api/v1/me", headers=bearer("user-a"))

            assert first.status_code == 200
            assert second.status_code == 200

            async with database.session_factory() as session:
                count = await session.scalar(select(func.count()).select_from(AuthSession))
                observed = await session.scalar(select(AuthSession))
                assert count == 1
                assert observed is not None
                expiry = observed.expires_at
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=UTC)
                assert int(expiry.timestamp()) == claims.exp
                assert observed.user_id is not None

    asyncio.run(scenario())


def test_missing_supabase_session_identifier_is_not_invented() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id=None)
        async with api_client({"user-a": claims}) as (client, database, _):
            response = await client.get("/api/v1/me", headers=bearer("user-a"))

            assert response.status_code == 200
            async with database.session_factory() as session:
                count = await session.scalar(select(func.count()).select_from(AuthSession))
                assert count == 0

    asyncio.run(scenario())


def test_revoked_internal_session_is_rejected() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="revoked-session")
        async with api_client({"user-a": claims}) as (client, database, _):
            first = await client.get("/api/v1/me", headers=bearer("user-a"))
            assert first.status_code == 200

            async with database.session_factory() as session:
                observed = await session.scalar(select(AuthSession))
                assert observed is not None
                observed.revoked_at = datetime.now(UTC)
                await session.commit()

            response = await client.get("/api/v1/me", headers=bearer("user-a"))

            assert response.status_code == 401
            assert response.json()["error"]["code"] == "SESSION_REVOKED"

    asyncio.run(scenario())
