"""Absolute financial execution boundary tests; no financial action is performed."""

import asyncio

from tests.helpers import api_client, bearer, make_claims
from tests.phase2_helpers import grant_payload, proposal, scope


def test_finance_execute_without_permission_is_denied() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="finance-no-permission", aal="aal2")
        request_scope = scope("finance", "place_order", ["account-a"])
        async with api_client({"owner": claims}) as (client, _, _):
            response = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("finance.execute", "place_order", request_scope),
            )
            assert response.json()["decision"] == "DENY"
            assert response.json()["reason_codes"] == ["NO_PERMISSION"]

    asyncio.run(scenario())


def test_finance_execute_permission_cannot_override_guard() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="finance-permission", aal="aal2")
        request_scope = scope("finance", "place_order", ["account-a"])
        async with api_client({"owner": claims}) as (client, _, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("finance.execute", request_scope),
            )
            response = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("finance.execute", "place_order", request_scope),
            )
            assert response.json()["decision"] == "DENY"
            assert response.json()["financial_guard_triggered"] is True
            assert response.json()["reason_codes"] == ["FINANCIAL_EXECUTION_BLOCKED"]

    asyncio.run(scenario())


def test_auto_execute_cannot_override_financial_guard() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="finance-auto-execute", aal="aal2")
        request_scope = scope("finance", "buy", ["account-a"])
        async with api_client({"owner": claims}) as (client, _, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("finance.execute", request_scope, auto_execute=True),
            )
            response = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("finance.execute", "buy", request_scope),
            )
            assert response.json()["decision"] == "DENY"
            assert response.json()["risk_level"] == 5

    asyncio.run(scenario())


def test_client_supplied_risk_cannot_lower_authoritative_risk() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="finance-client-risk", aal="aal2")
        request_scope = scope("finance", "sell", ["account-a"])
        async with api_client({"owner": claims}) as (client, _, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("finance.execute", request_scope),
            )
            top_level = proposal("finance.execute", "sell", request_scope)
            top_level["risk_level"] = 0
            rejected_input = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=top_level,
            )
            ignored_hint = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal(
                    "finance.execute",
                    "sell",
                    request_scope,
                    context={"risk_level": 0},
                ),
            )

            assert rejected_input.status_code == 422
            assert ignored_hint.json()["decision"] == "DENY"
            assert ignored_hint.json()["risk_level"] == 5
            assert ignored_hint.json()["financial_guard_triggered"] is True

    asyncio.run(scenario())


def test_finance_read_remains_distinct_and_can_be_allowed() -> None:
    async def scenario() -> None:
        claims = make_claims(session_id="finance-read", aal="aal2")
        request_scope = scope("finance", "read", ["account-a"])
        async with api_client({"owner": claims}) as (client, _, _):
            await client.post(
                "/api/v1/permissions/grant",
                headers=bearer("owner"),
                json=grant_payload("finance.read", request_scope),
            )
            response = await client.post(
                "/api/v1/authorization/evaluate",
                headers=bearer("owner"),
                json=proposal("finance.read", "read", request_scope),
            )

            assert response.json()["decision"] == "ALLOW"
            assert response.json()["risk_level"] == 2
            assert response.json()["financial_guard_triggered"] is False

    asyncio.run(scenario())
