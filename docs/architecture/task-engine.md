# Task Engine Architecture

Phase 3 persists and coordinates future work but performs no side effects. A verified identity and
a Phase 2 authorization decision are required before a Task is created. The Task Engine cannot
grant permissions, approve confirmations, lower risk, or bypass the financial guard.

`TaskStateMachine` is the single transition source for `PENDING`, `QUEUED`, the three waiting
states, `RUNNING`, and the four terminal states. Completed, failed, cancelled, and expired Tasks
cannot revive. RUNNING cancellation is rejected because Phase 3 has no cooperative Executor able
to prove that execution stopped.

ALLOW creates QUEUED work; confirmation creates WAITING_CONFIRMATION; permission-remediable denial
creates WAITING_PERMISSION. Invalid identity/capability/action, disabled capability, evaluation
failure, and financial execution are hard denies and persist no Task.

The normalized request fingerprint covers capability, action, scope, explicit device, priority,
expiry, retry bound, parent, and sanitized metadata. `UNIQUE(user_id, idempotency_key)` is the race
boundary. Mutations use conditional `(id, status, version)` updates and increment `version`.

TaskEvent is atomic append-oriented lifecycle history. AuditEvent is limited to security-relevant
creation, cancellation, and claim. TaskAttempt preserves future claim/completion/failure history.
FAILED is terminal; retry metadata is stored but no scheduler, queue, worker, or automatic retry
exists. PostgreSQL simultaneous-transaction behavior requires staging certification.
