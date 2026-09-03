# Phase 1 identity and authentication evidence

## Scope

Phase 1 implements authentication identity, JIT user provisioning, observed Supabase sessions,
owned devices, PostgreSQL persistence models, Alembic migration, initial RLS, MFA assurance
representation, and API v1 identity/device endpoints. Permissions, advanced audit, memory, AI,
voice, automation, financial behavior, and production integration remain outside scope.

## Implementation summary

- **TESTED:** Supabase JWT signature verification with a generated RSA key.
- **TESTED:** issuer, audience, expiry, required claims, token format, user role, and algorithm
  restriction.
- **TESTED:** JIT user creation, repeat-login idempotency, disabled-user rejection, and unique auth
  identity.
- **TESTED:** observed session creation, idempotency, expiry mapping, missing-session behavior, and
  internal revocation.
- **TESTED:** device registration, idempotent metadata refresh, listing, device context, revocation,
  invalid input, and cross-user isolation.
- **TESTED:** database unique, foreign-key, enum, and null constraints.
- **INSPECTED:** PostgreSQL RLS DDL and read-only privilege model.
- **REQUIRES STAGING:** PostgreSQL/Supabase runtime execution of the pgTAP RLS suite.

## Test summary

- Full pytest suite: **46 passed / 0 failed / 0 warnings**.
- Security/JWT/ownership subset: **31 passed / 0 failed**.
- Phase 0 foundation test files: **10 passed / 0 failed**.
- Ruff format/lint: **PASS**.
- Strict mypy across backend, shared, scripts, and tests: **PASS**.
- Compileall: **PASS**.

## Migration summary

The deterministic migration validator uses a fresh isolated database and performs:

1. upgrade from base to Alembic HEAD;
2. table presence verification;
3. Alembic model/schema parity check;
4. downgrade from HEAD to base;
5. removal verification for all Phase 1 tables;
6. re-upgrade to HEAD.

Result: **TESTED / PASS**. Production migrations do not call `Base.metadata.create_all()`.
`create_all()` appears only in isolated service tests.

## Authentication validation

The verifier accepts only `ES256` and `RS256`, requires `typ=JWT` and `kid`, obtains a public
key from a bounded cached JWKS client, and validates signature, exact issuer, configured audience,
expiry, UUID subject, and `role=authenticated`. Missing, malformed, expired, wrong-signature,
wrong-issuer, wrong-audience, unsupported-algorithm, and unavailable-JWKS cases are covered.

Supabase Auth remains the sole authentication authority. No password store, alternative token,
service-role operation, or production auth bypass exists.

## Device isolation

Backend queries always derive `user_id` from `IdentityContext`. Registration schemas forbid extra
ownership fields. Cross-user listing, device-header lookup, and revocation are **TESTED**. A revoked
device cannot be re-registered, and its mapped internal sessions are revoked.

## RLS status

- Migration statements: **INSPECTED**.
- Static policy/grant tests: **TESTED**.
- API ownership against the real service layer: **TESTED**.
- Supabase/PostgreSQL policy runtime: **REQUIRES STAGING**.

The transactional staging suite is
`infrastructure/supabase/tests/phase1_rls.test.sql`. It checks owner-only SELECT plus denial of
cross-user INSERT, UPDATE, and DELETE. No claim of runtime RLS certification is made locally.

## Security findings

- Dependency audit: **0 known vulnerabilities**.
- GitHub Actions audit: **0 findings**.
- Credential-pattern scan: **0 matches after removing a test-only PEM false positive**.
- CRITICAL/HIGH/MEDIUM/LOW: **0/0/0/0**.

## Known limitations

- Only asymmetric Supabase signing keys are supported; legacy `HS256` is intentionally rejected.
- No live Supabase Auth or PostgreSQL staging environment was authorized.
- RLS runtime and key-rotation behavior against a real Supabase project require staging.
- A device identifier/header is not cryptographic device attestation.
- Internal session revocation does not claim to revoke the canonical Supabase session globally.
- MFA flows and step-up policies are not implemented; only AAL representation is prepared.

## Regression status

Phase 0 application startup, health, settings, logging redaction, formatting, lint, typing, tests,
and compilation remain **PASS**. No Phase 2 capability was implemented.
