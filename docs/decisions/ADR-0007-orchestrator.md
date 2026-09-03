# ADR-0007: Deterministic Orchestrator coordinator

## Status

Accepted for Phase 6.

## Decision

Implement the Orchestrator inside the modular monolith as a typed, durable workflow coordinator.
Memory retrieval, AI routing/model selection, authorization/risk/confirmation, and Task lifecycle
remain owned by their certified services. Persist minimal workflow, immutable plan, transition, and
future-handoff evidence in migration `0007_orchestrator`.

Use a dedicated state machine rather than Task states, user-scoped idempotency plus normalized
request fingerprints, optimistic versions, and immutable plan hashes. Permit at most one action per
Phase 6 workflow to avoid partial multi-action authority. Server-owned modes are `NORMAL`,
`SAFE_MODE`, and `MAINTENANCE`; flags only restrict.

Reparse and recompute persisted plan evidence before any resumed confirmation or authorization
evaluation. A mismatch is a governance denial, not a recoverable plan mutation, and the old
confirmation is not consumed for altered content.

The future execution contract is an immutable internal envelope. It is neither public nor trusted
blindly and requires future Executor revalidation. No Executor, tool runner, queue, worker, agent
framework, or external integration is added.

## Rationale

This preserves explicit authority boundaries, prevents the Orchestrator from becoming a
supercomponent, closes idempotency/TOCTOU races, and keeps sensitive content out of durable
coordination data. It reuses existing service contracts and adds no dependency or infrastructure.

## Consequences

The default disabled model catalog means production orchestration cannot invoke a provider until a
later approved configuration exists. PostgreSQL concurrency and Supabase RLS remain staging
certification work. Multi-action composition, future execution, autonomous retries, and provider
operations remain out of scope.
