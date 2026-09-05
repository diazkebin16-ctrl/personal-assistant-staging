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

## Gemini candidate evaluation

Google Gemini 2.5 Flash-Lite is integrated as a second provider through the same `LLMProvider` and
`ProviderRegistry` boundary used by OpenAI. Its stable model id is `gemini-2.5-flash-lite`.

The initial integration is deliberately candidate-only: the model is enabled when its backend
credential is configured, has `evaluation_enabled=True`, and has `routing_enabled=False`. Therefore
it is available to the internal `CandidateEvaluator` but cannot be selected by `AIRoutingPolicy` and
cannot appear in the normal fallback chain. The evaluation path has no public endpoint and reuses
the same capability, context/output, and provider-specific sensitivity checks before invoking an
adapter.

Promotion to normal routing requires a later explicit server-side decision to set
`routing_enabled=True` after quality, latency, cost, privacy, and operational evidence has been
reviewed. Candidate status must not be represented by falsified price, health, quality, or
sensitivity metadata.

## Provider-specific privacy

Privacy approval is attached to each `ProviderDefinition`; approval for one external provider does
not authorize another. OpenAI retains its existing approval through `PRIVATE`. Gemini is initially
limited to `PUBLIC` and has no private, sensitive, or critical approval. `PRIVATE`, `SENSITIVE`, and
`CRITICAL` content therefore fails closed before a Gemini adapter can be invoked. No external
provider receives general access to user memory.

## Boundaries

- The default catalog contains disabled placeholders only. No external provider is operational
  without an explicitly approved server configuration and adapter.
- OpenAI and Gemini credentials are independently optional backend secrets. The absence of one does
  not disable the other; the absence of both preserves fail-closed behavior.
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

The Gemini adapter uses Google's current Google Gen AI SDK (`google-genai`) and the stable Gemini API
`v1` surface. Provider-specific SDK objects terminate at the adapter; the rest of the Router sees
only `ProviderRequest`, `ProviderResponse`, and neutral failure categories.
