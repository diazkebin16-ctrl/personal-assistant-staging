"""End-to-end Web Research authority, grounding, persistence, and idempotency flows."""

import asyncio
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai_router.policy import AIRoutingPolicy
from backend.app.ai_router.provider import FakeProvider, ProviderRegistry
from backend.app.ai_router.service import AIRouter
from backend.app.audit.engine import AuditEngine
from backend.app.core.config import Environment
from backend.app.orchestrator.enums import SafeMode
from backend.app.permissions.engine import PermissionsEngine
from backend.app.research.evidence import build_evidence
from backend.app.research.fetch import RawFetchResponse, SafeFetcher
from backend.app.research.policy import ResearchPolicy
from backend.app.research.provider import FakeSearchProvider, SearchProviderRegistry
from backend.app.research.schemas import FetchedDocument, SearchResult
from backend.app.research.service import ResearchService
from backend.app.research.url_safety import ResolvedTarget, URLSafetyPolicy
from backend.app.text_assistant.enums import AssistantOutcome
from backend.app.text_assistant.schemas import AssistantRequest, ConversationCreateRequest
from backend.app.text_assistant.service import TextAssistantService
from tests.helpers import isolated_database
from tests.phase5_helpers import identity, routing_catalog
from tests.phase6_helpers import add_identity_user, build_orchestrator, grant, provider_response


class PublicResolver:
    def resolve(self, host: str, port: int) -> tuple[str, ...]:
        del host, port
        return ("93.184.216.34",)


class CountingTransport:
    def __init__(self) -> None:
        self.call_count = 0

    async def request(
        self, target: ResolvedTarget, *, max_bytes: int, timeout: float
    ) -> RawFetchResponse:
        del target, max_bytes, timeout
        self.call_count += 1
        return RawFetchResponse(
            200,
            {"content-type": "text/plain; charset=utf-8"},
            b"Public standard version is thirteen.",
        )


def request(content: str, *, key: str = "research-message-key") -> AssistantRequest:
    return AssistantRequest(
        content=content,
        idempotency_key=key,
        expected_version=1,
        use_memory_context=False,
        requested_output_tokens=512,
    )


def synthesis_response() -> str:
    evidence = build_evidence(
        (
            FetchedDocument(
                canonical_url="https://example.com/report",
                title="Public report",
                text="Public standard version is thirteen.",
                retrieved_at=datetime(2026, 9, 2, tzinfo=UTC),
            ),
        ),
        "public standard",
    )
    return json.dumps(
        {
            "claims": [
                {
                    "text": "The public standard version is thirteen.",
                    "evidence_ids": [evidence[0].evidence_id],
                }
            ]
        }
    )


def build_service(
    session: AsyncSession,
    *,
    safe_mode: SafeMode = SafeMode.NORMAL,
    enabled: bool = True,
) -> tuple[
    TextAssistantService,
    FakeSearchProvider,
    CountingTransport,
    dict[str, FakeProvider],
]:
    orchestrator, _ = build_orchestrator(session, (), safe_mode=safe_mode)
    catalog = routing_catalog()
    response = provider_response(synthesis_response())
    ai_providers = {
        key: FakeProvider(key, (response,))
        for key in ("primary", "equivalent", "sensitive-approved", "local-approved")
    }
    router = AIRouter(
        session,
        catalog,
        AIRoutingPolicy(catalog),
        providers=ProviderRegistry(ai_providers.values()),
    )
    search = FakeSearchProvider(
        (
            (
                SearchResult(
                    url="https://example.com/report",
                    title="Public report",
                    snippet="Public standard",
                    rank=1,
                ),
            ),
        )
    )
    transport = CountingTransport()
    audit = AuditEngine(session)
    research = ResearchService(
        router,
        PermissionsEngine(session, audit),
        audit,
        ResearchPolicy(enabled=enabled, safe_mode=safe_mode),
        SearchProviderRegistry((search,), environment=Environment.LOCAL),
        SafeFetcher(URLSafetyPolicy(PublicResolver()), transport=transport),  # type: ignore[arg-type]
    )
    orchestrator.research_service = research
    assistant = TextAssistantService(session, orchestrator.memory, router, orchestrator)
    return assistant, search, transport, ai_providers


def test_research_success_persists_server_constructed_citations() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                await grant(session, current, "web.research", "search", "web")
                service, search, transport, ai = build_service(session)
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                result = await service.submit(
                    current, conversation.id, request("search public standard")
                )
                message = result.assistant_message
                assert message.outcome is AssistantOutcome.RESEARCH_ANSWERED
                assert message.citations[0].url == "https://example.com/report"
                assert message.citations[0].citation_id in message.content
                assert search.call_count == transport.call_count == 1
                assert sum(provider.call_count for provider in ai.values()) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("content", "outcome"),
    [
        ("search public standard", AssistantOutcome.RESEARCH_PERMISSION_REQUIRED),
        ("research public standard", AssistantOutcome.RESEARCH_PERMISSION_REQUIRED),
    ],
)
def test_missing_permission_prevents_all_outbound_work(
    content: str, outcome: AssistantOutcome
) -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                service, search, transport, ai = build_service(session)
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                result = await service.submit(current, conversation.id, request(content))
                assert result.assistant_message.outcome is outcome
                assert search.call_count == transport.call_count == 0
                assert sum(provider.call_count for provider in ai.values()) == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", [SafeMode.SAFE_MODE, SafeMode.MAINTENANCE])
def test_safe_modes_prevent_outbound_work(mode: SafeMode) -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                await grant(session, current, "web.research", "search", "web")
                service, search, transport, _ = build_service(session, safe_mode=mode)
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                result = await service.submit(
                    current, conversation.id, request("search public standard")
                )
                assert result.assistant_message.outcome is AssistantOutcome.RESEARCH_POLICY_DENIED
                assert search.call_count == transport.call_count == 0

    asyncio.run(scenario())


def test_sensitive_input_is_rejected_before_outbound_work() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                await grant(session, current, "web.research", "search", "web")
                service, search, transport, _ = build_service(session)
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                result = await service.submit(
                    current,
                    conversation.id,
                    request("search api_key=secret public standard"),
                )
                assert result.assistant_message.outcome is AssistantOutcome.RESEARCH_POLICY_DENIED
                assert search.call_count == transport.call_count == 0

    asyncio.run(scenario())


def test_disabled_research_is_truthful_and_makes_no_calls() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                service, search, transport, _ = build_service(session, enabled=False)
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                result = await service.submit(
                    current, conversation.id, request("search public standard")
                )
                assert result.assistant_message.outcome is AssistantOutcome.RESEARCH_UNAVAILABLE
                assert result.assistant_message.reason_code == "RESEARCH_DISABLED"
                assert search.call_count == transport.call_count == 0

    asyncio.run(scenario())


def test_replayed_message_is_idempotent_without_repeating_network_work() -> None:
    async def scenario() -> None:
        async with isolated_database() as database:
            async with database.session_factory() as session:
                current = identity()
                await add_identity_user(session, current)
                await grant(session, current, "web.research", "search", "web")
                service, search, transport, _ = build_service(session)
                conversation = await service.create_conversation(
                    current, ConversationCreateRequest()
                )
                command = request("search public standard")
                first = await service.submit(current, conversation.id, command)
                second = await service.submit(current, conversation.id, command)
                assert first.assistant_message.id == second.assistant_message.id
                assert search.call_count == transport.call_count == 1

    asyncio.run(scenario())


def test_client_cannot_supply_research_mode_or_provider() -> None:
    payload = request("search public standard").model_dump()
    payload["research_mode"] = "NO_RESEARCH"
    payload["provider"] = "attacker-controlled"
    with pytest.raises(ValidationError):
        AssistantRequest.model_validate(payload)
