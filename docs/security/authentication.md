# Authentication security

## Trust model

Only a Supabase Auth access token that passes local asymmetric verification establishes identity.
The internal profile and session tables observe that identity; they do not authenticate passwords
or replace Supabase sessions.

Required checks:

- compact JWT format and bounded token size;
- `typ=JWT` and non-empty `kid`;
- algorithm allowlist: `ES256`, `RS256`;
- JWKS public-key signature;
- exact configured issuer;
- configured audience;
- non-expired `exp`;
- UUID `sub`;
- `role=authenticated`.

Legacy/shared-secret `HS256` verification is intentionally unsupported. Authentication fails
closed when JWKS retrieval or configuration is unavailable.

## Secrets and logging

Raw JWTs, authorization headers, access/refresh tokens, service-role keys, passwords, and private
keys are excluded from application logs and public responses. Structured logs may include only the
internal `user_id` and validated `device_id`.

The anon key is client configuration under the Supabase model, not administrative authority. The
service-role key is server-only, remains optional, and is unused by this phase.

## Sessions and devices

An observed session row is created only when the verified token provides a reliable `session_id`.
Internal revocation rejects that session locally but does not claim to revoke Supabase globally.

A device header is a lookup handle, not authentication proof. It is checked against the verified
user, revocation state, and any established session-device binding. Registering the same installation
is idempotent. Revoking a device retains its record and revokes mapped internal sessions.

## Test authentication

Tests replace the verifier and database dependencies through FastAPI dependency overrides. There is
no runtime environment flag, route, or production code path that disables authentication.
