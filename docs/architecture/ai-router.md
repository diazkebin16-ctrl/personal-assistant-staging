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
   unapproved models. Models marked `routing_enabled=False` are not exposed to normal routing or
   fallback selection.
4. The policy selects the smallest sufficient quality tier deterministically. Cost breaks ties only
   between equivalent sufficient candidates.
5. The selected decision and bounded fallback chain are persisted without prompts or responses.
6. An optional provider call uses a bounded adapter chain. Each attempt writes privacy-safe usage
   telemetry; provider output has no execution authority.

## Evaluation-only model candidates

Evaluation candidates reuse the normal provider boundary but remain excluded from normal routing and
fallback. `gpt-5-nano` is currently registered under the existing OpenAI provider with
`evaluation_enabled=True` and `routing_enabled=False`. The same OpenAI credential, sensitivity
policy, accounting boundary, and privacy rules apply. Luna remains the normal FAST model until a
later reviewed routing decision explicitly changes that policy.

`CandidateEvaluator` can explicitly compare an evaluation candidate with an already-routable
baseline such as Luna. This does not promote the candidate or alter the baseline. Evaluation records
provider success/failure, returned token usage including cached input when available, latency,
estimated catalog cost, and ephemeral response text. Raw benchmark prompts are not logged.

## Provider-specific privacy

OpenAI retains its existing approval through `PRIVATE`. Candidate status does not broaden that
approval: `SENSITIVE` and `CRITICAL` continue to fail closed for external OpenAI models, and context
or Memory is released only through the existing Text Assistant permission and relevance gates.

## Boundaries

- The default catalog contains disabled placeholders only. No external provider is operational
  without explicitly approved server configuration and an adapter.
- OpenAI credentials remain an optional backend secret; their absence preserves fail-closed behavior.
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

## Provider SDKs

The OpenAI adapter uses the Responses API through the existing OpenAI SDK. Provider-specific SDK
objects terminate at the adapter; the rest of the Router sees only `ProviderRequest`,
`ProviderResponse`, and neutral failure categories.
