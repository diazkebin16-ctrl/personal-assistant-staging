"""Internal AI Router orchestration, bounded fallback, and privacy-safe usage accounting."""

import logging
from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai_router.catalog import ModelCatalog
from backend.app.ai_router.enums import (
    FailureCategory,
    RoutingOutcome,
    RoutingReason,
    UsageOutcome,
)
from backend.app.ai_router.models import AIUsageRecord, RoutingDecisionRecord
from backend.app.ai_router.observability import (
    AIRoutingMetricEvent,
    AIRoutingObserver,
    NullAIRoutingObserver,
)
from backend.app.ai_router.policy import AIRoutingPolicy, CostUsageSnapshot
from backend.app.ai_router.provider import ProviderFailure, ProviderRegistry
from backend.app.ai_router.schemas import (
    AIExecutionResult,
    ModelReference,
    ProviderAttemptFailure,
    ProviderHealthSnapshot,
    ProviderRequest,
    ProviderResponse,
    RoutingDecision,
    RoutingRequest,
)
from backend.app.audit.engine import AuditEngine
from backend.app.audit.schemas import AuditRecord
from backend.app.core.errors import AIProviderExecutionError, AIRoutingDeniedError
from backend.app.identity.context import IdentityContext
from backend.app.permissions.enums import ActorType, AuditEventType, AuditResult

logger = logging.getLogger(__name__)

_AUDITED_DENIALS = frozenset(
    {
        RoutingReason.SENSITIVITY_RESTRICTION,
        RoutingReason.HARD_BUDGET_EXCEEDED,
        RoutingReason.LOCAL_ONLY_REQUIRED,
    }
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded foreground attempt policy; no background worker is created."""

    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 10:
            raise ValueError("AI provider attempts must be between 1 and 10")


class AIRouter:
    """Internal service boundary; it exposes no public prompt proxy or model override."""

    def __init__(
        self,
        session: AsyncSession,
        catalog: ModelCatalog,
        policy: AIRoutingPolicy,
        *,
        providers: ProviderRegistry | None = None,
        retry_policy: RetryPolicy | None = None,
        observer: AIRoutingObserver | None = None,
    ) -> None:
        self.session = session
        self.catalog = catalog
        self.policy = policy
        self.providers = providers or ProviderRegistry(())
        self.retry_policy = retry_policy or RetryPolicy()
        self.observer = observer or NullAIRoutingObserver()
        self.audit = AuditEngine(session)

    async def route(
        self,
        identity: IdentityContext,
        request: RoutingRequest,
        *,
        health: ProviderHealthSnapshot | None = None,
        cost_usage: CostUsageSnapshot | None = None,
    ) -> RoutingDecision:
        decision = self.policy.decide(identity.user_id, request, health, cost_usage)
        self.session.add(self._decision_record(decision, request))
        await self.session.flush()

        if decision.outcome is RoutingOutcome.DENIED:
            await self._audit_denial(identity, decision)
            logger.warning(
                "AI routing denied by server policy",
                extra={
                    "user_id": str(identity.user_id),
                    "task_id": str(request.task_id) if request.task_id else None,
                    "decision_id": str(decision.id),
                },
            )
            self.observer.emit(
                AIRoutingMetricEvent(
                    name="ai.routing.denied",
                    attributes={
                        "decision_id": str(decision.id),
                        "reason": decision.reason_codes[0].value,
                        "sensitivity": decision.effective_sensitivity.value,
                    },
                )
            )
        else:
            selected = decision.selected_model
            if selected is None:
                raise AIRoutingDeniedError
            logger.info(
                "AI routing decision selected",
                extra={
                    "user_id": str(identity.user_id),
                    "task_id": str(request.task_id) if request.task_id else None,
                    "decision_id": str(decision.id),
                    "provider_key": selected.provider_key,
                    "model_id": selected.model_id,
                    "model_class": selected.model_class.value,
                    "fallback_count": len(decision.fallback_chain),
                    "estimated_cost_microunits": decision.estimated_cost_microunits,
                },
            )
            self.observer.emit(
                AIRoutingMetricEvent(
                    name="ai.routing.selected",
                    attributes={
                        "decision_id": str(decision.id),
                        "provider_key": selected.provider_key,
                        "model_id": selected.model_id,
                        "model_class": selected.model_class.value,
                        "fallback_count": len(decision.fallback_chain),
                        "estimated_cost_microunits": (decision.estimated_cost_microunits or 0),
                    },
                )
            )
        return decision

    async def invoke(
        self,
        identity: IdentityContext,
        request: RoutingRequest,
        provider_request: ProviderRequest,
        *,
        health: ProviderHealthSnapshot | None = None,
        cost_usage: CostUsageSnapshot | None = None,
    ) -> AIExecutionResult:
        """Execute a bounded fake/configured adapter chain; never executes tools or actions."""
        if (
            provider_request.output_token_budget > request.requested_output_tokens
            or (
                provider_request.structured_output_required
                and not request.structured_output_required
            )
            or provider_request.tool_calling_required
            and not request.tool_calling_required
        ):
            raise AIRoutingDeniedError
        decision = await self.route(identity, request, health=health, cost_usage=cost_usage)
        if decision.outcome is RoutingOutcome.DENIED:
            raise AIRoutingDeniedError

        selected = decision.selected_model
        if selected is None:
            raise AIRoutingDeniedError
        chain = (selected, *decision.fallback_chain)
        failures: list[ProviderAttemptFailure] = []

        for attempt_number, model_ref in enumerate(
            chain[: self.retry_policy.max_attempts], start=1
        ):
            started = perf_counter()
            try:
                provider = self.providers.get(model_ref.provider_key)
                response = await provider.generate(model_ref.model_id, provider_request)
                if response.output_tokens > provider_request.output_token_budget:
                    raise ProviderFailure(FailureCategory.MALFORMED_RESPONSE)
            except ProviderFailure as exc:
                latency_ms = max(0, round((perf_counter() - started) * 1000))
                await self._record_failure_usage(
                    identity,
                    decision,
                    request,
                    model_ref,
                    attempt_number,
                    latency_ms,
                    exc.category,
                )
                failures.append(
                    ProviderAttemptFailure(
                        model=model_ref,
                        category=exc.category,
                        retryable=exc.retryable,
                    )
                )
                self.observer.emit(
                    AIRoutingMetricEvent(
                        name="ai.provider.attempt",
                        attributes={
                            "provider_key": model_ref.provider_key,
                            "model_id": model_ref.model_id,
                            "attempt": attempt_number,
                            "latency_ms": latency_ms,
                            "success": False,
                            "failure_category": exc.category.value,
                        },
                    )
                )
                if not exc.retryable:
                    break
                continue

            latency_ms = max(0, round((perf_counter() - started) * 1000))
            await self._record_success_usage(
                identity,
                decision,
                request,
                model_ref,
                attempt_number,
                latency_ms,
                response,
            )
            self.observer.emit(
                AIRoutingMetricEvent(
                    name="ai.provider.attempt",
                    attributes={
                        "provider_key": model_ref.provider_key,
                        "model_id": model_ref.model_id,
                        "attempt": attempt_number,
                        "latency_ms": latency_ms,
                        "success": True,
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                    },
                )
            )
            return AIExecutionResult(
                routing_decision=decision,
                final_model=model_ref,
                response=response,
                failures=tuple(failures),
            )

        raise AIProviderExecutionError

    async def list_usage(
        self,
        identity: IdentityContext,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AIUsageRecord]:
        """Internal owner-scoped telemetry query; no public API is registered."""
        bounded_limit = min(max(limit, 1), 100)
        bounded_offset = max(offset, 0)
        statement: Select[tuple[AIUsageRecord]] = (
            select(AIUsageRecord)
            .where(AIUsageRecord.user_id == identity.user_id)
            .order_by(AIUsageRecord.timestamp.desc(), AIUsageRecord.id.desc())
            .limit(bounded_limit)
            .offset(bounded_offset)
        )
        return list((await self.session.scalars(statement)).all())

    @staticmethod
    def _decision_record(
        decision: RoutingDecision,
        request: RoutingRequest,
    ) -> RoutingDecisionRecord:
        selected = decision.selected_model
        return RoutingDecisionRecord(
            id=decision.id,
            user_id=decision.user_id,
            task_id=decision.task_id,
            outcome=decision.outcome,
            provider_key=selected.provider_key if selected else None,
            model_id=selected.model_id if selected else None,
            model_class=selected.model_class if selected else None,
            selected_quality=int(selected.quality_tier) if selected else None,
            policy_version=decision.policy_version,
            reason_codes=[reason.value for reason in decision.reason_codes],
            required_capabilities=[item.value for item in decision.required_capabilities],
            effective_sensitivity=decision.effective_sensitivity,
            estimated_input_tokens=request.estimated_input_tokens,
            requested_output_tokens=request.requested_output_tokens,
            fallback_chain=[item.model_dump(mode="json") for item in decision.fallback_chain],
            estimated_cost_microunits=decision.estimated_cost_microunits,
            created_at=decision.created_at,
        )

    async def _audit_denial(
        self,
        identity: IdentityContext,
        decision: RoutingDecision,
    ) -> None:
        if not _AUDITED_DENIALS.intersection(decision.reason_codes):
            return
        await self.audit.record(
            AuditRecord(
                user_id=identity.user_id,
                device_id=identity.device_id,
                session_id=identity.session_id,
                actor_type=ActorType.SYSTEM,
                event_type=AuditEventType.AI_ROUTING_DENIED,
                result=AuditResult.DENIED,
                resource_type="ai_routing_decision",
                resource_id=str(decision.id),
                reason_codes=tuple(reason.value for reason in decision.reason_codes),
                task_id=decision.task_id,
                metadata={"sensitivity": decision.effective_sensitivity.value},
            )
        )

    async def _record_success_usage(
        self,
        identity: IdentityContext,
        decision: RoutingDecision,
        request: RoutingRequest,
        model_ref: ModelReference,
        attempt_number: int,
        latency_ms: int,
        response: ProviderResponse,
    ) -> None:
        model = self.catalog.model(model_ref)
        estimated = model.pricing.estimate_microunits(
            response.input_tokens,
            response.output_tokens,
        )
        self.session.add(
            AIUsageRecord(
                user_id=identity.user_id,
                task_id=request.task_id,
                routing_decision_id=decision.id,
                provider_key=model_ref.provider_key,
                model_id=model_ref.model_id,
                attempt_number=attempt_number,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cached_tokens=response.cached_tokens,
                latency_ms=latency_ms,
                outcome=UsageOutcome.SUCCESS,
                failure_category=None,
                estimated_cost_microunits=estimated,
                actual_cost_microunits=response.actual_cost_microunits,
            )
        )
        await self.session.flush()

    async def _record_failure_usage(
        self,
        identity: IdentityContext,
        decision: RoutingDecision,
        request: RoutingRequest,
        model_ref: ModelReference,
        attempt_number: int,
        latency_ms: int,
        category: FailureCategory,
    ) -> None:
        model = self.catalog.model(model_ref)
        estimated = model.pricing.estimate_microunits(
            request.estimated_input_tokens,
            request.requested_output_tokens,
        )
        self.session.add(
            AIUsageRecord(
                user_id=identity.user_id,
                task_id=request.task_id,
                routing_decision_id=decision.id,
                provider_key=model_ref.provider_key,
                model_id=model_ref.model_id,
                attempt_number=attempt_number,
                input_tokens=0,
                output_tokens=0,
                cached_tokens=0,
                latency_ms=latency_ms,
                outcome=UsageOutcome.FAILURE,
                failure_category=category,
                estimated_cost_microunits=estimated,
                actual_cost_microunits=None,
            )
        )
        await self.session.flush()
