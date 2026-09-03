# Permissions and Authorization API

All routes require the verified Phase 1 bearer-token dependency.

## Evaluate

`POST /api/v1/authorization/evaluate`

Input contains `capability_key`, `action`, structured `scope`, optional safe `resource` and
bounded `context`, and an optional action-bound `confirmation_id`. It does not accept identity,
permission results, grant source, or authoritative risk. The response is an immutable decision
containing IDs, reason codes, risk, confirmation state, scope match, and financial-guard status.

## Permission center

- `GET /api/v1/permissions`
- `GET /api/v1/permissions/{permission_id}`
- `POST /api/v1/permissions/grant`
- `POST /api/v1/permissions/{permission_id}/revoke`

Grant is the AAL2 own-account bootstrap boundary. The server sets owner and
`USER_EXPLICIT` source. Responses include controlled capability metadata, scope, device, status,
policy, lifecycle timestamps, reason, `auto_execute`, and last relevant use. Capability metadata
includes the server-owned `allowed_actions` vocabulary. A grant containing any other operation
is rejected with `422 ACTION_NOT_ALLOWED`.

Authorization repeats the capability/action check and returns `DENY` with
`ACTION_NOT_ALLOWED` if an invalid pair is proposed or found in a malformed legacy permission.

## Confirmation

- `POST /api/v1/confirmations/{confirmation_id}/approve`
- `POST /api/v1/confirmations/{confirmation_id}/reject`

Both are AAL2 and owner-scoped. `EVERY_TIME` and high-risk per-action approvals are consumed by a
matching re-evaluation and cannot be replayed. `ONCE` records initial consent for that permission.

No route executes the proposed action.
