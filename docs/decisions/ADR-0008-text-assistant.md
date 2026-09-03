# ADR-0008: Bounded conversational interface over certified authority domains

## Decision

Persist owner-scoped conversations separately from Memory. Construct model context from complete,
bounded recent messages plus a `MemoryService` context pack, propagate the highest sensitivity to
`AIRouter`, and delegate action-shaped requests to `OrchestratorService`. Use versioned central
system instructions, `(user, idempotency key)` uniqueness, a semantic request fingerprint, and
optimistic conversation versioning.

Explicit `remember`, recall, and forget commands use the existing Memory authority path. No
autonomous memory inference or Executor is introduced. Phase 7 intentionally defers conversation
summarization because a safe model-governed summarizer is not yet certified.

## Rationale

This preserves a natural single-assistant experience while keeping provider/model selection,
sensitivity, permissions, risk, confirmation, Task state, Safe Mode, financial safeguards, and
future execution outside conversational authority. Whole-message bounds avoid security-changing
partial truncation, and telemetry remains privacy-safe.

