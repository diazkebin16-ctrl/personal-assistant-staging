# Text Assistant API

All endpoints require the existing authenticated `IdentityContext`. Ownership is derived on the
server; `user_id`, provider, model, risk, sensitivity, permission, confirmation state, and Safe
Mode cannot be supplied as authority.

- `POST /api/v1/conversations` creates an owner-scoped conversation.
- `GET /api/v1/conversations` lists owned conversations with bounded pagination.
- `GET /api/v1/conversations/{id}` returns one owned conversation or a non-leaking 404.
- `POST /api/v1/conversations/{id}/messages` submits an idempotent message with an expected
  conversation version.
- `GET /api/v1/conversations/{id}/messages` returns bounded visible history in sequence order.

The message response includes persisted user and assistant messages plus truthful outcome data.
There is no raw completion, provider/model override, system-prompt, execution, tool, or force-state
endpoint.

