"""Phase 5 authority, privacy, leakage, and cross-domain boundary tests."""

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from backend.app.ai_router.enums import Complexity
from backend.app.ai_router.models import AIUsageRecord
from backend.app.ai_router.policy import AIRoutingPolicy
from backend.app.ai_router.provider import FakeProvider, ProviderRegistry
from backend.app.ai_router.schemas import ProviderRequest, ProviderResponse, RoutingRequest
from backend.app.ai_router.service import AIRouter
from backend.app.identity.models import User
from backend.app.security.classification import DataSensitivity
from tests.helpers import api_client, isolated_database
from tests.phase5_helpers import identity, routing_catalog

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def safe_request() -> RoutingRequest:
    return RoutingRequest(
        task_type="assistant.response",
        complexity=Complexity.LOW,
        sensitivity=DataSensitivity.PRIVATE,
        estimated_input_tokens=10,
        requested_output_tokens=10,
    )


def test_no_public_arbitrary_prompt_model_or_provider_proxy_exists() -> None:
    async def scenario() -> None:
        async with api_client({}) as (client, _database, _application):
            for path in (
                "/api/v1/ai/completions",
                "/api/v1/ai/route",
                "/api/v1/providers/primary/generate",
                "/api/v1/models/fast/complete",
            ):
                response = await client.post(
                    path,
                    json={
                        "prompt": "unrestricted",
                        "force_model": "hidden-model",
                        "ignore_sensitivity": True,
                    },
                )
                assert response.status_code == 404

    asyncio.run(scenario())


def test_routing_contract_rejects_provider_model_cost_health_and_sensitivity_bypasses() -> None:
    base = safe_request().model_dump(mode="json")
    attacks: tuple[tuple[str, object], ...] = (
        ("model", "hidden-model"),
        ("provider", "disabled"),
        ("force_model", "advanced"),
        ("force_provider", "primary"),
        ("ignore_sensitivity", True),
        ("provider_health", {"disabled": "AVAILABLE"}),
        ("estimated_cost", 0),
        ("actual_cost", 0),
        ("hard_budget", 10**12),
    )
    for field, value in attacks:
        with pytest.raises(ValidationError):
            RoutingRequest.model_validate({**base, field: value})


def test_raw_prompt_is_absent_from_repr_logs_and_usage_telemetry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive_prompt = "CRITICAL memory credential marker-not-for-logs"
    provider_request = ProviderRequest(input_text=sensitive_prompt, output_token_budget=10)
    assert sensitive_prompt not in repr(provider_request)

    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                session.add(User(id=current.user_id, auth_user_id=current.auth_user_id))
                await session.flush()
                catalog = routing_catalog()
                router = AIRouter(
                    session,
                    catalog,
                    AIRoutingPolicy(catalog),
                    providers=ProviderRegistry(
                        (
                            FakeProvider(
                                "primary",
                                (
                                    ProviderResponse(
                                        output_text="safe",
                                        input_tokens=5,
                                        output_tokens=1,
                                    ),
                                ),
                            ),
                        )
                    ),
                )
                await router.invoke(current, safe_request(), provider_request)
                usage = await session.scalar(select(AIUsageRecord))
                assert usage is not None
                assert "prompt" not in AIUsageRecord.__table__.columns
                assert "content" not in AIUsageRecord.__table__.columns

    asyncio.run(scenario())
    assert sensitive_prompt not in caplog.text
    assert "marker-not-for-logs" not in caplog.text


def test_router_has_no_memory_database_task_executor_or_permission_mutation_coupling() -> None:
    package = PROJECT_ROOT / "backend/app/ai_router"
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    forbidden_imports = (
        "backend.app.memory.models",
        "backend.app.memory.service",
        "backend.app.tasks.service",
        "backend.app.permissions.service",
        "backend.app.permissions.engine",
    )
    for import_name in forbidden_imports:
        assert import_name not in source
    for authority_method in (
        "execute_tool",
        "execute_task",
        "grant_permission",
        "approve_confirmation",
        "persist_memory",
        "finance_execute",
    ):
        assert authority_method not in source


def test_tool_capability_is_selection_metadata_with_zero_execution_authority() -> None:
    request = RoutingRequest(
        task_type="future.tool-aware-response",
        complexity=Complexity.MEDIUM,
        sensitivity=DataSensitivity.PUBLIC,
        estimated_input_tokens=10,
        requested_output_tokens=10,
        tool_calling_required=True,
    )
    decision = AIRoutingPolicy(routing_catalog()).decide(identity().user_id, request)
    assert decision.selected_model is not None
    assert decision.selected_model.model_id == "standard"
    assert "tool_calls" not in ProviderResponse.model_fields
    assert "permission_granted" not in ProviderResponse.model_fields
    assert "execute" not in ProviderResponse.model_fields


def test_critical_memory_label_fails_closed_before_any_external_provider_invocation() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                session.add(User(id=current.user_id, auth_user_id=current.auth_user_id))
                await session.flush()
                catalog = routing_catalog()
                external = FakeProvider(
                    "primary",
                    (
                        ProviderResponse(
                            output_text="must not run", input_tokens=1, output_tokens=1
                        ),
                    ),
                )
                router = AIRouter(
                    session,
                    catalog,
                    AIRoutingPolicy(catalog),
                    providers=ProviderRegistry((external,)),
                )
                critical = RoutingRequest(
                    task_type="assistant.response",
                    complexity=Complexity.MEDIUM,
                    sensitivity=DataSensitivity.PUBLIC,
                    context_sensitivities=(DataSensitivity.CRITICAL,),
                    estimated_input_tokens=10,
                    requested_output_tokens=10,
                )
                from backend.app.core.errors import AIRoutingDeniedError

                with pytest.raises(AIRoutingDeniedError):
                    await router.invoke(
                        current,
                        critical,
                        ProviderRequest(input_text="critical memory", output_token_budget=10),
                    )
                assert external.call_count == 0

    asyncio.run(scenario())
