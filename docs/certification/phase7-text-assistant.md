# Phase 7 certification evidence

## TESTED

Final local certification: 563 tests passed, including 132 security tests, with zero failures or
warnings. Ruff format/lint, strict mypy, compileall, application startup, health checks, Alembic
upgrade/downgrade/re-upgrade, and dependency audit passed.

- Authenticated conversation creation, text response, persistence, owner isolation, pagination,
  message sequencing, idempotent retry, changed-payload conflict, and stale-version rejection.
- Bounded recent history without deleting visible history.
- Explicit Memory save through `MemoryService`; deletion confirmation truthfulness.
- Effective-sensitivity propagation and `CRITICAL` fail-closed routing before provider invocation.
- AI Router-only provider selection, Orchestrator action flow, malformed/failure-safe behavior, no
  Executor, financial hard deny, prompt-injection inertness, and privacy-safe telemetry.
- Clean migration upgrade, downgrade/re-upgrade, and model/schema drift check.

## STATICALLY VALIDATED

- PostgreSQL RLS policy definitions and Phase 7 pgTAP coverage.
- Database uniqueness/check/FK constraints and historical migration immutability.

## REQUIRES STAGING

- Supabase RLS runtime execution and live JWT/JWKS behavior.
- PostgreSQL-specific simultaneous idempotency and optimistic-update race certification.

## NOT APPLICABLE

- Live provider credentials, external tools, Executor, financial execution, voice, browser,
  messaging, calendar writes, device control, and BotsTrader/OANDA integrations.
