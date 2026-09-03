# AI Router architecture

Phase 5 adds an internal, provider-independent routing boundary. It selects the smallest model
that satisfies a server-owned quality floor, capability requirements, sensitivity policy, health,
context/output bounds, and explicit budgets. It does not interpret global intent, retrieve memory,
execute tools, mutate permissions, create tasks, or perform external actions.

## Flow

1. A future Orchestrator supplies a validated `RoutingRequest` and verified `IdentityContext`.
2. `AIRoutingPolicy` derives the required model class and effective sensitivity. Context labels can
   raise sensitivity but can never lower it.
3. The immutable `ModelCatalog` filters disabled, deprecated, unhealthy, incapable, undersized, or
   unapproved models.
4. The policy selects the smallest sufficient quality tier deterministically. Cost breaks ties only
   between equivalent sufficient candidates.
5. The selected decision and bounded fallback chain are persisted without prompts or responses.
6. An optional provider call uses a bounded adapter chain. Each attempt writes privacy-safe usage
   telemetry; provider output has no execution authority.

## Boundaries

- The default catalog contains disabled placeholders only. No external provider is operational
  without an explicitly approved server configuration and adapter.
- The Router receives context metadata, never unrestricted Memory database access.
- FAST may escalate to STANDARD or ADVANCED; an unavailable advanced model never silently degrades
  to FAST.
- REALTIME, EMBEDDING, and LOCAL are catalog classes only. Phase 5 starts no audio session, creates
  no vector, and downloads no local model.
- No public prompt/completion/model-override API is registered.
- No response cache exists; cross-user cache safety therefore cannot be violated in this phase.

## Persistence and concurrency

`ai_routing_decisions` is immutable evidence for selection or denial. `ai_usage_records` is
append-oriented per-attempt telemetry with a unique `(routing_decision_id, attempt_number)`
constraint. The catalog and provider registry expose no mutation API; provider health and aggregate
budgets arrive as immutable trusted snapshots. No distributed consensus or background retry worker
is introduced.

## Future integration

Phase 6 will own intent and context construction. A future OpenTelemetry adapter can consume the
privacy-safe observer events. Real provider contracts, credentials, live health monitoring,
realtime transport, embedding generation, and vector dimension selection remain later work.

