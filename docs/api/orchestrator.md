# Orchestrator API

All routes require the existing verified Supabase identity. Owner, device authority, AAL,
permission, risk, confirmation satisfaction, provider/model, sensitivity, safe mode, state, and
execution authority are not accepted from request bodies.

- `POST /api/v1/orchestrations`: submit a bounded intent label/category, ephemeral input,
  idempotency key, bounded context selection, output budget, and optional expiry.
- `GET /api/v1/orchestrations`: owner-only list with state and bounded pagination filters.
- `GET /api/v1/orchestrations/{workflow_id}`: owner-only safe workflow metadata.
- `POST /api/v1/orchestrations/{workflow_id}/cancel`: optimistic owner cancellation; a linked Task
  must also reach its certified cancelled state.
- `POST /api/v1/orchestrations/{workflow_id}/resume`: reevaluate only permission/confirmation wait
  states through TaskService using an expected workflow version.

Informational answers are returned ephemerally and are not persisted. Public responses contain no
prompt, Memory text, provider response history, permission scope internals, or execution envelope.
There is no arbitrary plan, state, model, provider, confirmation, or execution endpoint.
