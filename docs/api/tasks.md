# Tasks API

All routes require the verified Phase 1 identity.

- `POST /api/v1/tasks`: create or idempotently resolve work after Phase 2 authorization.
- `GET /api/v1/tasks`: list owned Tasks with bounded pagination and simple filters.
- `GET /api/v1/tasks/{task_id}`: return an owned Task with attempts and events.
- `POST /api/v1/tasks/{task_id}/cancel`: cancel owned cancellable work with expected version.

Creation accepts capability, action, scope, idempotency key, optional owned device, priority,
expiry, retry bound, parent, and bounded metadata. Owner, state, authorization, risk, completion,
claim, and execution authority are never accepted from clients. No public state, claim, completion,
failure, retry, TaskEvent mutation, or Executor route exists.
