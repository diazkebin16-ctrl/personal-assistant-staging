# Phase 4 Memory Certification Evidence

## TESTED

- Five canonical classes, explicit statuses, source vocabulary, sensitivity, confidence/importance,
  content/time/metadata bounds, and database constraints.
- Explicit user provenance, Task provenance ownership, device ownership/revocation, and denial of
  future-AI persistence.
- Exact normalized deduplication, database uniqueness, per-user independence, and distinct
  historical decisions.
- Versioned updates, stale-write denial, reconstructable revisions, immutable historical decisions,
  archive, repeat archive, privacy delete, repeat delete, deleted-content/revision scrubbing, and no
  resurrection.
- Lazy temporary expiration, active/archived/expired/discardable retrieval behavior, bounded
  filters/pagination, and maximum-20 deterministic context-pack design.
- Default-deny permissions, server-owned memory actions, delete risk/confirmation, confirmation
  replay denial, capability/action and financial regression.
- Cross-user API isolation, spoofing, oversized/nested payload denial, safe audit/event metadata,
  migration round-trips, schema/model alignment, and Phase 0–4 regression.

## STATICALLY VALIDATED

- `0005_memory_core` RLS allows owner SELECT, excludes deleted content, and grants no authenticated
  writes on memory, revisions, or events.
- pgTAP covers cross-user records/revisions/events and direct owner/provenance/state/history
  mutation denial.
- Conditional PostgreSQL version/status updates and the partial unique index define concurrency
  boundaries.

## REQUIRES STAGING

- Runtime Supabase RLS, simultaneous PostgreSQL duplicate/update/archive/delete races, and live
  Supabase JWT/JWKS validation.

## NOT TESTED

- Production load, retention cleanup, or semantic retrieval quality.

## NOT APPLICABLE

- OpenAI, embedding generation, pgvector dimension/index, semantic ranking, AI Router,
  Orchestrator, autonomous extraction, voice, external integrations, and Task execution.

No public state/provenance/embedding control, cross-user access, deletion resurrection, parallel
permission/risk/confirmation system, external service change, or production side effect is present.

Final local validation: **247 passed, 0 failed, 0 warnings**; security suite: **56 passed, 0
failed**. Ruff format/lint, strict mypy, compileall, application import/lifespan health tests,
migration/schema drift checks, and dependency audit passed. `pip-audit` found no known
vulnerabilities; the local project package is not a PyPI dependency and was skipped as expected.
