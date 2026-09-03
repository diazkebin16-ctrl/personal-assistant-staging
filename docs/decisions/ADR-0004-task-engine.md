# ADR-0004: Task Engine Core

## Decision

Use one canonical state machine, user-scoped idempotency with a normalized SHA-256 fingerprint and
database uniqueness, and conditional optimistic updates using Task `version`. Preserve lifecycle
history in TaskEvent and future execution history in TaskAttempt. Use AuditEvent only for
security-relevant creation, cancellation, and claim.

ALLOW maps to QUEUED, confirmation to WAITING_CONFIRMATION, and remediable permission denial to
WAITING_PERMISSION. Hard denial creates no Task. FAILED remains terminal; retry metadata is only
represented. A future controlled worker may atomically claim QUEUED work, but Phase 3 contains no
Executor, queue, leases, scheduler, or side effects.

## Consequences

RUNNING cancellation waits for a cooperative future Executor. PostgreSQL concurrency and RLS
runtime certification require staging; SQLite evidence is not presented as that certification.
