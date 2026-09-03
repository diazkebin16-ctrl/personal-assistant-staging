# ADR-0006: AI Router

## Decision

Use a deterministic provider-independent Router with an immutable server-owned code/config catalog.
Canonical model classes are FAST, STANDARD, ADVANCED, REALTIME, EMBEDDING, and LOCAL. Routing is
quality-first, sensitivity-aware, capability-aware, bounded by model context/output limits, and
fail-closed.

Persist privacy-safe routing decisions and usage attempts through Alembic `0006_ai_router`; keep
catalog configuration outside the database initially. No provider is enabled by default. Use an
adapter protocol and deterministic fake provider for Phase 5 validation.

## Rationale

- A single policy prevents provider-specific routing leakage and client-controlled model selection.
- The smallest sufficient model preserves quality while avoiding unnecessary cost.
- Explicit provider/model sensitivity approval prevents MemoryContextPack leakage.
- Equivalent provider fallback improves reliability without silent quality degradation.
- Immutable decisions, append-oriented usage, structured observer events, and selective audit make
  routing explainable without retaining content.

## Detailed consequences

- Complexity is distinct from risk, task priority, sensitivity, and importance.
- FAST → STANDARD → ADVANCED escalation is deterministic. No subjective LLM self-grading exists.
- Context is never truncated by the Router; the future Orchestrator owns reduction/summarization.
- Structured-output/tool requirements filter models; model tool output has zero action authority.
- Pricing is versioned operational metadata. Soft budgets observe; configured hard limits deny.
- Provider health is a trusted immutable snapshot, not request input.
- Catalog/model enablement acts as a restrictive feature flag and never bypasses hard policy.
- No response cache is introduced.
- REALTIME, LOCAL runtime, embedding generation, vector dimension, and live providers are deferred.
- Phase 6 constructs authoritative requests and context; the Router never queries raw Memory.

## Privacy and staging

Decision/usage tables omit prompts and outputs. PostgreSQL RLS permits owner SELECT and denies direct
client mutation. Policies and pgTAP are statically validated locally; live Supabase RLS and live
provider privacy/configuration remain `REQUIRES STAGING`.

