"""Canonical Web Research pipeline with bounded retrieval and grounded synthesis."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError

from backend.app.ai_router.enums import Complexity, ModelCapability
from backend.app.ai_router.schemas import ProviderRequest, RoutingRequest
from backend.app.ai_router.service import AIRouter
from backend.app.audit.engine import AuditEngine
from backend.app.audit.schemas import AuditRecord
from backend.app.identity.context import IdentityContext
from backend.app.permissions.engine import PermissionsEngine
from backend.app.permissions.enums import (
    ActorType,
    AuditEventType,
    AuditResult,
    AuthorizationDecisionType,
)
from backend.app.permissions.schemas import AuthorizationRequest, PermissionScope
from backend.app.research.cache import BoundedTTLCache
from backend.app.research.enums import ResearchErrorCode, ResearchMode
from backend.app.research.errors import ResearchError
from backend.app.research.evidence import build_evidence, synthesis_prompt, validate_synthesis
from backend.app.research.extract import extract_document
from backend.app.research.fetch import SafeFetcher
from backend.app.research.observability import (
    NullResearchObserver,
    ResearchMetricEvent,
    ResearchObserver,
)
from backend.app.research.policy import POLICY_VERSION, ResearchPolicy
from backend.app.research.provider import SearchProviderRegistry
from backend.app.research.schemas import (
    FetchedDocument,
    ResearchAnswer,
    SearchResult,
    SynthesisEnvelope,
)
from backend.app.security.classification import DataSensitivity

logger = logging.getLogger(__name__)
_ACTION_BY_MODE = {
    ResearchMode.SEARCH: "search",
    ResearchMode.FETCH: "fetch",
    ResearchMode.MULTI_SOURCE_RESEARCH: "multi_source",
}


class ResearchService:
    """One authority-preserving route from assistant request to cited answer."""

    def __init__(
        self,
        ai_router: AIRouter,
        permissions: PermissionsEngine,
        audit: AuditEngine,
        policy: ResearchPolicy,
        providers: SearchProviderRegistry,
        fetcher: SafeFetcher,
        *,
        observer: ResearchObserver | None = None,
    ) -> None:
        self.ai_router = ai_router
        self.permissions = permissions
        self.audit = audit
        self.policy = policy
        self.providers = providers
        self.fetcher = fetcher
        self.observer = observer or NullResearchObserver()
        self._document_cache: BoundedTTLCache[FetchedDocument] = BoundedTTLCache()

    async def research(
        self,
        identity: IdentityContext,
        *,
        content: str,
        sensitivity: DataSensitivity,
        requested_output_tokens: int,
        confirmation_id: UUID | None = None,
    ) -> ResearchAnswer:
        mode = self.policy.select_mode(content)
        if mode is ResearchMode.NO_RESEARCH:
            raise ResearchError(ResearchErrorCode.POLICY_DENIED)
        action = _ACTION_BY_MODE[mode]
        if not self.policy.enabled:
            await self._audit_rejection(identity, mode, ResearchErrorCode.DISABLED)
            raise ResearchError(ResearchErrorCode.DISABLED)
        if not self.policy.permits_external_access(sensitivity):
            await self._audit_rejection(identity, mode, ResearchErrorCode.POLICY_DENIED)
            raise ResearchError(ResearchErrorCode.POLICY_DENIED)

        decision = await self.permissions.authorize(
            identity,
            AuthorizationRequest(
                capability_key="web.research",
                action=action,
                scope=PermissionScope(resource_type="web", operations=[action]),
                context={"mode": mode.value, "policy_version": POLICY_VERSION},
                confirmation_id=confirmation_id,
            ),
        )
        if decision.decision is AuthorizationDecisionType.REQUIRE_CONFIRMATION:
            raise ResearchError(
                ResearchErrorCode.CONFIRMATION_REQUIRED,
                confirmation_id=decision.confirmation_id,
            )
        if decision.decision is not AuthorizationDecisionType.ALLOW:
            raise ResearchError(ResearchErrorCode.PERMISSION_REQUIRED)

        self.observer.emit(
            ResearchMetricEvent(
                name="research.requested",
                attributes={"mode": mode.value, "policy_version": POLICY_VERSION},
            )
        )
        try:
            answer = await asyncio.wait_for(
                self._execute(
                    identity,
                    mode,
                    content,
                    sensitivity,
                    requested_output_tokens,
                ),
                timeout=self.policy.budget.total_timeout_seconds,
            )
        except TimeoutError:
            await self._audit_rejection(identity, mode, ResearchErrorCode.FETCH_TIMEOUT)
            raise ResearchError(ResearchErrorCode.FETCH_TIMEOUT) from None
        except ResearchError as exc:
            await self._audit_rejection(identity, mode, exc.code)
            raise
        self.observer.emit(
            ResearchMetricEvent(
                name="research.completed",
                attributes={
                    "mode": mode.value,
                    "source_count": len(answer.citations),
                    "cache_enabled": True,
                },
            )
        )
        return answer

    async def _execute(
        self,
        identity: IdentityContext,
        mode: ResearchMode,
        content: str,
        sensitivity: DataSensitivity,
        requested_output_tokens: int,
    ) -> ResearchAnswer:
        query = self.policy.minimize_query(content)
        if not query:
            raise ResearchError(ResearchErrorCode.INSUFFICIENT_EVIDENCE)
        results: tuple[SearchResult, ...]
        if mode is ResearchMode.FETCH:
            url = self.policy.direct_url(content)
            if url is None:
                raise ResearchError(ResearchErrorCode.BLOCKED_URL)
            results = (SearchResult(url=url, title="Direct source", rank=1),)
        else:
            search_limit = 3 if mode is ResearchMode.SEARCH else self.policy.budget.max_sources
            results = await self._search(query, search_limit)

        documents: list[FetchedDocument] = []
        seen: set[str] = set()
        total_bytes = 0
        for result in results[: self.policy.budget.max_fetches]:
            try:
                canonical = self.fetcher.safety.canonicalize(result.url)
                if canonical in seen:
                    continue
                seen.add(canonical)
                key = self._document_cache.key(canonical)
                cached = self._document_cache.get(key)
                if cached:
                    documents.append(cached.value)
                    continue
                final_url, content_type, body = await self.fetcher.fetch(canonical)
                total_bytes += len(body)
                if total_bytes > self.policy.budget.max_total_bytes:
                    raise ResearchError(ResearchErrorCode.CONTENT_TOO_LARGE)
                title, text = extract_document(
                    body,
                    content_type,
                    max_chars=self.policy.budget.max_extracted_chars,
                )
                document = FetchedDocument(
                    canonical_url=final_url,
                    title=title if title != "Untitled source" else result.title,
                    text=text,
                    retrieved_at=datetime.now(UTC),
                )
                self._document_cache.put(key, document)
                documents.append(document)
            except ResearchError:
                if mode is ResearchMode.FETCH:
                    raise
                continue
            if len(documents) >= self.policy.budget.max_sources:
                break
        evidence = build_evidence(
            documents,
            query,
            limit=self.policy.budget.max_evidence_items,
        )
        if not evidence:
            raise ResearchError(ResearchErrorCode.INSUFFICIENT_EVIDENCE)

        prompt = synthesis_prompt(query, evidence)
        routing = RoutingRequest(
            task_type="text_assistant.web_research",
            complexity=(
                Complexity.HIGH if mode is ResearchMode.MULTI_SOURCE_RESEARCH else Complexity.MEDIUM
            ),
            required_capabilities=frozenset(
                {ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_OUTPUT}
            ),
            sensitivity=sensitivity,
            estimated_input_tokens=max(1, (len(prompt) + 3) // 4),
            requested_output_tokens=requested_output_tokens,
            structured_output_required=True,
            tool_calling_required=False,
        )
        from backend.app.core.errors import AIProviderExecutionError, AIRoutingDeniedError

        try:
            execution = await self.ai_router.invoke(
                identity,
                routing,
                ProviderRequest(
                    input_text=prompt,
                    output_token_budget=requested_output_tokens,
                    structured_output_required=True,
                    tool_calling_required=False,
                ),
            )
        except (AIProviderExecutionError, AIRoutingDeniedError):
            raise ResearchError(ResearchErrorCode.PROVIDER_UNAVAILABLE) from None
        try:
            parsed = SynthesisEnvelope.model_validate_json(execution.response.output_text)
        except (ValidationError, ValueError, json.JSONDecodeError):
            raise ResearchError(ResearchErrorCode.MALFORMED_SYNTHESIS) from None
        content_out, citations = validate_synthesis(parsed, evidence)
        return ResearchAnswer(
            mode=mode,
            content=content_out,
            citations=citations,
            routing_decision_id=execution.routing_decision.id,
        )

    async def _search(self, query: str, limit: int) -> tuple[SearchResult, ...]:
        provider = self.providers.default()
        last_error = ResearchError(ResearchErrorCode.PROVIDER_UNAVAILABLE)
        for _ in range(self.policy.budget.max_provider_attempts):
            try:
                return await asyncio.wait_for(
                    provider.search(query, limit),
                    timeout=self.policy.budget.fetch_timeout_seconds,
                )
            except TimeoutError:
                last_error = ResearchError(ResearchErrorCode.SEARCH_TIMEOUT)
            except ResearchError as exc:
                last_error = exc
                if exc.code not in {
                    ResearchErrorCode.PROVIDER_UNAVAILABLE,
                    ResearchErrorCode.SEARCH_TIMEOUT,
                }:
                    break
        raise last_error

    async def _audit_rejection(
        self,
        identity: IdentityContext,
        mode: ResearchMode,
        code: ResearchErrorCode,
    ) -> None:
        await self.audit.record(
            AuditRecord(
                user_id=identity.user_id,
                device_id=identity.device_id,
                session_id=identity.session_id,
                actor_type=ActorType.SYSTEM,
                event_type=AuditEventType.ORCHESTRATION_SECURITY_REJECTED,
                result=AuditResult.DENIED,
                capability_key="web.research",
                action=_ACTION_BY_MODE[mode],
                resource_type="web",
                reason_codes=(code.value,),
                metadata={"mode": mode.value, "policy_version": POLICY_VERSION},
            )
        )
        logger.warning(
            "Web Research request rejected",
            extra={"user_id": str(identity.user_id), "mode": mode.value, "reason": code.value},
        )
