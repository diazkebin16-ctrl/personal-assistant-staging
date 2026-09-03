# Phase 5 certification evidence

## Scope

Provider-independent model catalog, deterministic routing, quality escalation, sensitivity policy,
context/output limits, bounded fallbacks, provider health, cost estimation/budgets, immutable
decisions, privacy-safe usage, observability adapter, selective audit, and restrictive RLS.

## TESTED

- All six canonical model classes and catalog validation.
- Complexity-to-quality routing and smallest-sufficient selection.
- Structured output, tool capability, realtime, embedding, and local requirements.
- Provider AVAILABLE/DEGRADED/UNAVAILABLE/DISABLED behavior.
- PUBLIC/INTERNAL/PRIVATE/SENSITIVE policies and CRITICAL fail-closed/local-only behavior.
- MemoryContextPack sensitivity escalation; no sensitivity downgrade.
- Context/output escalation and denial without truncation.
- Equivalent fallback, exhaustion, permanent failure, retry bounds, and no weak degradation.
- Estimated versus nullable actual cost, equivalent-cost optimization, request/daily/monthly budgets.
- Decision/usage persistence, owner queries, DB invariants, audit denial, telemetry without content.
- No public prompt/model/provider API and no cross-domain execution authority.
- Clean migration, downgrade/re-upgrade, schema/model alignment, startup, health, and Phase 0-5
  regression.

## STATICALLY VALIDATED

- PostgreSQL RLS ownership and mutation-denial SQL.
- pgTAP coverage for cross-user routing/usage isolation and direct mutation denial.
- Historical migration checksums for `0001` through `0005` are unchanged.

## REQUIRES STAGING

- Live Supabase RLS/pgTAP execution.
- Live Supabase JWT/JWKS validation inherited from Phase 1.
- Real provider credentials, contractual privacy/data-retention approval, live provider health,
  token accounting, latency, billing, and error mapping.
- PostgreSQL-specific concurrent telemetry behavior.

## NOT TESTED

- Real model quality, realtime/audio, embeddings, local runtime, and external provider APIs because
  Phase 5 deliberately performs no external model call.

## NOT APPLICABLE

- Orchestrator, autonomous tools, external side effects, financial execution, response caching,
  workers, queues, and Phase 6 functionality.

## Security findings

CRITICAL: 0. HIGH: 0. MEDIUM: 0. LOW: 0.

## Latest local validation

- Phase 5 focused matrix: 58 passed, 0 failed.
- Full Phase 0–5 suite: 305 passed, 0 failed, 0 warnings.
- Security suite: 64 passed, 0 failed.
- Ruff format/lint, strict mypy, compileall, application startup, health, and Alembic validation:
  PASS.
- Dependency audit: no known vulnerabilities; the local `personal-assistant` package is not a PyPI
  dependency and is reported as skipped by the auditor.
