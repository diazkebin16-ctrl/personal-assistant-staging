# ADR-0012: Offline state is transport, not authority

- Status: Accepted
- Date: 2026-09-02
- Phase: 11 — Offline System

## Context

The Phase 8 client already has one encrypted pending-message record and one WorkManager delivery
route. Phase 11 must survive longer outages, process death, duplicate execution, ambiguous server
commit, and multi-device conflict without creating a second queue or trusting stale local policy.

## Decision

Evolve the existing record and repository. Use a typed state machine, authoritative user/device
binding, authenticated payload integrity, atomic claims, bounded allowlisted retry, serialized
event-driven recovery, and the existing server idempotency contract. Local cache and pending state
remain labeled representations. New submissions always enter the current canonical server path.

Do not add a generic local operation executor, offline LLM, authority cache, raw-audio upload queue,
cloud Wake fallback, backend table, or reconciliation endpoint. Identical idempotent resubmission is
sufficient because the Text Assistant checks an existing key/fingerprint before optimistic version.

## Consequences

The client can queue Text intent safely and converge after response loss while preserving exactly one
delivery authority. An expired session requires user action and policy conflicts terminate visibly.
Legacy pending rows without provable owner/device binding cannot replay. Cancellation after a send
starts may remain explicitly ambiguous instead of pretending that either cancellation or acceptance
occurred.

