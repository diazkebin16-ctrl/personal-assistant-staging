# Identity API v1

All endpoints below require `Authorization: Bearer <Supabase access token>`. Clients may include
`X-Device-ID: <internal device UUID>` after registration.

## GET /api/v1/me

Returns the safe internal user ID, display name, resolved device ID, authentication state, and
authentication assurance level. It never returns token or Supabase service metadata.

## POST /api/v1/devices/register

Accepted fields:

- `device_name`: 1–100 characters;
- `device_type`: ANDROID, IOS, WEB, DESKTOP, WATCH, or UNKNOWN;
- `platform`: bounded platform identifier;
- `device_identifier`: stable non-secret installation identifier;
- `capabilities`: up to 32 boolean manifest entries and 4 KiB encoded;
- `public_key`: optional, maximum 4096 characters; private keys are rejected.

Ownership is always taken from the verified identity. Supplying `user_id`, `authenticated`, or a
role is rejected. Re-registering the same `(user, device_identifier)` updates permitted metadata
and preserves the device UUID.

## GET /api/v1/devices

Returns only devices owned by the authenticated user. Public-key material and device identifiers
are not echoed.

## POST /api/v1/devices/{device_id}/revoke

Revokes an owned device idempotently and locally revokes its mapped observed sessions. Another
user's device is returned as not found.

## Errors

Responses use `{"error":{"code":"...","message":"..."}}` with 401 for missing/invalid
authentication, 403 for disabled/revoked state, 404 for unavailable devices, 409 for identity
conflicts, and 422 for invalid device input. Stack traces, SQL details, tokens, and secrets are never
included.
