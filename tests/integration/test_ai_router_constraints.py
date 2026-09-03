"""Database-backed AI routing and usage invariants."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.ai_router.enums import Complexity, UsageOutcome
from backend.app.ai_router.models import AIUsageRecord
from backend.app.ai_router.policy import AIRoutingPolicy
from backend.app.ai_router.schemas import RoutingRequest
from backend.app.ai_router.service import AIRouter
from backend.app.identity.models import User
from backend.app.security.classification import DataSensitivity
from tests.helpers import isolated_database
from tests.phase5_helpers import identity, routing_catalog


def test_denied_decision_cannot_smuggle_a_selected_provider_or_model() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                user = User(auth_user_id=uuid4())
                session.add(user)
                await session.flush()
                with pytest.raises(IntegrityError):
                    await session.execute(
                        text(
                            "INSERT INTO ai_routing_decisions ("
                            "id, user_id, outcome, provider_key, model_id, policy_version, "
                            "reason_codes, required_capabilities, effective_sensitivity, "
                            "estimated_input_tokens, requested_output_tokens, fallback_chain"
                            ") VALUES ("
                            ":id, :user_id, 'DENIED', 'injected', 'injected', 'v1', "
                            "'[]', '[]', 'PUBLIC', 0, 1, '[]'"
                            ")"
                        ),
                        {"id": uuid4().hex, "user_id": user.id.hex},
                    )
                    await session.commit()

    asyncio.run(scenario())


def test_usage_attempt_number_is_unique_per_routing_decision() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                session.add(User(id=current.user_id, auth_user_id=current.auth_user_id))
                await session.flush()
                catalog = routing_catalog()
                decision = await AIRouter(session, catalog, AIRoutingPolicy(catalog)).route(
                    current,
                    RoutingRequest(
                        task_type="assistant.response",
                        complexity=Complexity.LOW,
                        sensitivity=DataSensitivity.PUBLIC,
                        estimated_input_tokens=1,
                        requested_output_tokens=1,
                    ),
                )
                common = {
                    "user_id": current.user_id,
                    "routing_decision_id": decision.id,
                    "provider_key": "primary",
                    "model_id": "fast",
                    "attempt_number": 1,
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cached_tokens": 0,
                    "latency_ms": 1,
                    "outcome": UsageOutcome.SUCCESS,
                    "failure_category": None,
                    "estimated_cost_microunits": 1,
                    "actual_cost_microunits": None,
                }
                session.add_all([AIUsageRecord(**common), AIUsageRecord(**common)])
                with pytest.raises(IntegrityError):
                    await session.commit()

    asyncio.run(scenario())
