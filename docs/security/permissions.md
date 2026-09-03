# Permission Security

Authorization is default-deny and always evaluates the verified `IdentityContext`. Client bodies
cannot select an owner or assert authorization.

## Grant lifecycle

- User-facing grants require AAL2 and are recorded as `USER_EXPLICIT`.
- No `LLM_GRANTED`, administrator bypass, trusted-AI flag, or implicit broad grant exists.
- Temporary grants are denied at `now >= expires_at`; a cron job is not a security dependency.
- Revocation is immediate, idempotent, audited, and preserves the row.
- A disabled capability denies all related authorization regardless of grants.
- Device-scoped grants require the same owned, non-revoked device.

## Scope

Scope is a validated object containing `resource_type`, bounded `resource_ids`, and bounded
`operations`. Requested operations and resources must be a subset of the grant. Reading one
resource cannot silently authorize another resource or a write operation.

The capability catalog owns the valid action vocabulary. Grant-time validation rejects any
scope operation absent from `Capability.allowed_actions`; authorization repeats this check before
risk classification and inspects persisted permission operations defensively. Consequently,
scope may narrow authority but cannot invent it. Invalid capability/action pairs use the
structured `ACTION_NOT_ALLOWED` code and fail closed.

Examples: `finance.read + buy` is invalid at the capability boundary, while
`finance.execute + buy` is a valid pair that remains denied by the independent financial guard.

## Failure policy

Database and required-audit failures return a safe service error and roll back the transaction.
Risk or safety-classifier exceptions produce a denied decision when auditability remains
available. No failure mode returns an authorization that was not fully established.
