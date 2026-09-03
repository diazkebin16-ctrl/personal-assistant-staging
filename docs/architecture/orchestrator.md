# Orchestrator architecture

Phase 6 adds a modular-monolith coordinator, not a privileged executor. Its fixed sequence is:

1. verified `IdentityContext` and owner-scoped idempotency;
2. bounded `MemoryService.build_context_pack` selection;
3. effective sensitivity propagation to `AIRouter`;
4. ephemeral provider invocation through the selected adapter;
5. strict `CandidatePlan` validation and immutable fingerprinting;
6. `TaskService.create`, which retains Capability/Permissions/Risk/Confirmation/Financial Guard
   authority;
7. workflow state and append-oriented step evidence;
8. optional immutable `AuthorizedActionEnvelope` for a future Executor to revalidate.

The Orchestrator does not query Memory tables, model catalogs, permissions tables, or confirmation
tables directly. `PermissionsEngine.capability_allows` exposes the server-owned action vocabulary,
and `get_owned_decision` exposes immutable evidence. Task creation remains the only actionable
authority path.

## Lifecycle separation

Orchestration states describe coordination: `RECEIVED`, `CONTEXT_PREPARED`, `ROUTED`,
`PROPOSAL_GENERATED`, `PLAN_VALIDATED`, waiting states, `READY_FOR_EXECUTION`, and terminal
outcomes. Task states describe durable work execution readiness and lifecycle. An orchestration
ready state only means a Task is `QUEUED`; it never means an action executed.

Terminal orchestration states cannot revive. `READY_FOR_EXECUTION` may only expire or be cancelled
in Phase 6. A future executor must add an approved completion linkage rather than reinterpret this
state.

## Plans, idempotency, and concurrency

Public requests are fingerprinted from normalized intent, a SHA-256 of ephemeral input, context
selection, output bound, and expiry. `UNIQUE(user_id, idempotency_key)` closes create races; the same
key with different semantics conflicts. State mutations use `version`-guarded atomic updates, and
each transition appends an `OrchestrationStep` in the same transaction.

One Phase 6 workflow may contain zero informational actions or exactly one actionable proposal.
Rejecting multi-action plans avoids partial authorization and confirmation ambiguity before a
future workflow-composition design is approved. The stored validated plan is immutable. Material
arguments are included in its fingerprint, so confirmation cannot be reused for a modified plan.
On resume, the Orchestrator reparses and rehashes the stored payload before authority reevaluation;
any mismatch with both stored and workflow fingerprints becomes `PLAN_INTEGRITY_FAILURE`. This
check occurs before an approved confirmation can be consumed.

## Memory and model content

Memory context is owner-authorized, at most 20 items, excludes archived/deleted/expired records,
and preserves class, provenance, sensitivity, importance, and bounded text. User input is
conservatively `PRIVATE`; Memory may only raise sensitivity. The Router selects a model before the
ephemeral prompt reaches a provider. Raw prompts, responses, and Memory content are not persisted.

## Safe modes and future boundary

`NORMAL` permits policy-compliant action coordination. `SAFE_MODE` permits informational flows but
blocks actionable readiness. `MAINTENANCE` denies new workflows. Feature flags only restrict.

`AuthorizedActionEnvelope` contains identity, workflow, Task, canonical action, inert arguments,
scope/plan fingerprints, permission/decision/confirmation references, risk result, safe-mode and
policy versions, idempotency, and expiry. It has no public creation route and grants no authority;
the future Executor must independently revalidate all evidence.
