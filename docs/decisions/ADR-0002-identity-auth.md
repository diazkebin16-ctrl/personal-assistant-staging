# ADR-0002: Supabase identity and authentication

- Status: Accepted
- Date: 2026-09-01

## Decision

Use Supabase Auth as the sole authentication authority and map verified Supabase user UUIDs to
internal PostgreSQL profiles. Verify asymmetric Supabase JWTs locally through cached JWKS discovery.
Model known devices and observed Supabase sessions without storing credentials or issuing tokens.

Authentication and authorization remain separate. Phase 1 produces an immutable identity context;
Phase 2 will decide permissions. Supabase MFA assurance claims are represented without adding
step-up policy. PostgreSQL RLS provides owner isolation as defense in depth and does not replace
backend ownership checks.

## Rationale

This preserves one source of authentication truth, supports signing-key rotation, avoids putting the
Auth service in every request's hot path, and prevents premature provider coupling through a full
SDK. Internal UUID models provide stable references for future multi-device capabilities while
retaining simple modular-monolith operation.

## Consequences

- Deployments require asymmetric Supabase signing keys exposed through JWKS.
- Legacy `HS256` projects must migrate signing keys before using this verifier.
- Missing token `session_id` remains absent rather than being synthesized.
- Device identifiers remain installation hints, not strong device attestation.
- PostgreSQL RLS runtime certification requires an authorized staging environment.
- No permission, risk, financial, or advanced audit policy is introduced.
