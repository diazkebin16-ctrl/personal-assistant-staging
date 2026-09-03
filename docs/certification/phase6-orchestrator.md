# Phase 6 certification evidence

## Scope

Typed durable orchestration, bounded Memory context, sensitivity-preserving AI routing, strict plan
proposals, Task/authority integration, immutable plan and future handoff evidence, safe modes,
idempotency, concurrency, audit, observability, RLS, and a narrow owner API. No external execution.

## TESTED

- Exhaustive declared/undeclared orchestration transition matrix and terminal protection.
- Informational no-Task flow and ephemeral answers.
- Owner isolation, idempotent replay, changed-payload conflict, stale versions, cancellation, and
  lazy expiry.
- Memory permission boundary; excluded expired/deleted memory; CRITICAL context routing denial.
- AI Router selection/invocation using deterministic fake adapters only; malformed output failure.
- Strict authority-field rejection, unknown capability/action rejection, prompt-injection
  non-authority, and no public force/executor/envelope route.
- Permission wait, confirmation wait/approval, immutable plan fingerprint, authorized Task linkage,
  and future envelope creation.
- Plan-content rehash before confirmation consumption; materially changed plans fail closed with no
  envelope.
- Financial hard deny across buy, sell, transfer, withdraw, deposit, place order, leverage/risk
  changes, and generic execution, including permission-then-reevaluation paths.
- Safe mode, feature-flag non-bypass, device ownership, privacy-safe persistence/audit/usage,
  migration drift, startup, health, and Phase 0–6 regression.

Final local results: `526 passed`, including `105 passed` in the security suite, with zero pytest
warnings. Format, Ruff lint, mypy over 145 source files, compileall, startup, both health endpoints,
migration validation, and dependency audit all passed.

## STATICALLY VALIDATED

- `0007_orchestrator` PostgreSQL RLS and owner-read/backend-write-only grants.
- Phase 6 pgTAP coverage for cross-user workflows/plans/steps/envelopes and mutation denial.
- Historical migration SHA-256 values for `0001`–`0006` remain byte-identical.

## REQUIRES STAGING

- Live Supabase RLS/pgTAP execution and inherited live JWT/JWKS validation.
- PostgreSQL simultaneous idempotency, optimistic-transition, cancellation/readiness, and
  confirmation race certification.
- Real provider privacy approval, credentials, responses, quality, latency, and failure mapping.

## NOT TESTED

- External actions, real tools, autonomous workflows, background workers, queues, realtime voice,
  browser/device agents, communications, and financial execution because Phase 6 forbids them.

## Security findings

CRITICAL: 0. HIGH: 0. MEDIUM: 0. LOW: 0.

## Certification status

Local evidence is complete. Supabase/PostgreSQL runtime assertions remain explicitly
`REQUIRES STAGING` and are not represented as runtime PASS.
