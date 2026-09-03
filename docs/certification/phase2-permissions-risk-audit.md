# Phase 2 Certification Evidence

## Scope

Phase 2 implements the decision boundary only: capability-plus-action-plus-scope permissions, deterministic
risk, confirmation, financial execution denial, and audit. No executor, Task Engine, queue,
worker, AI, external integration, deployment, or production modification was introduced.

## TESTED

- Full suite: 96 passed, 0 failed, 0 warnings after the 0.2.1 security correction and final
  refactor.
- Capability/action correction matrix: 14 new tests cover five valid pairs, five invalid pairs at
  both grant and authorization, a valid financial execution pair blocked by the financial guard,
  two malformed legacy grants, and direct risk rejection.
- Permission matrix: default deny, valid grant, expiry, revocation, disabled capability, scope,
  device scope, revoked device, disabled user, confirmation policies, and `auto_execute` limits.
- Risk matrix: levels 0–5 and deterministic privacy, external, destructive, and financial floors.
- Confirmation matrix: creation, approval, rejection, expiry, cross-user denial, action binding,
  ONCE semantics, per-action consumption, and replay denial.
- Financial matrix: no permission, valid permission, `auto_execute`, client risk manipulation,
  financial guard, and independently allowed scoped read.
- Audit: allow/deny/revoke/confirmation/financial events, owner isolation, append-only API,
  metadata redaction/limits, and transactional rollback on required-audit failure.
- Migration: clean upgrade through `0001`, `0002`, and `0003`; metadata comparison; safe
  correction downgrade/re-upgrade; safe downgrade to Phase 1; downgrade to base; and final
  re-upgrade.
- Phase 0 and Phase 1 regression, JWT, identity, device isolation, health, and redaction.

## STATICALLY VALIDATED

- Phase 2 RLS enables policies for all user-owned tables, grants only SELECT to `authenticated`,
  exposes only enabled global capabilities, and grants no direct INSERT/UPDATE/DELETE.
- The staging SQL covers cross-user SELECT and blocked cross-user writes.
- Alembic reports no schema/model drift.
- Audit mutation routes do not exist.
- `Capability.allowed_actions` is the single runtime authority source. Grant and authorization
  reuse the model membership rule; no per-capability conditionals or secondary action blacklist
  exist in runtime code.
- Patch-pattern and architecture review is performed before final packaging.

## REQUIRES STAGING

- Runtime PostgreSQL/Supabase execution of both pgTAP RLS suites.
- Live Supabase JWT/JWKS behavior remains the inherited Phase 1 staging gate.

## NOT TESTED

- Hosted Supabase, Railway, or GitHub remote behavior; external modification is prohibited.
- Production load and concurrency against PostgreSQL.

## NOT APPLICABLE

- Financial execution, money movement, general executor, Task Engine, external integrations, LLM,
  memory, voice, workers, and queues.

## Security findings

No known Critical, High, Medium, or Low security finding remained after the final regression.
`pip-audit` reported no known dependency vulnerabilities, the offline GitHub Actions audit
reported no findings, and the credential-pattern scan was clean. The artifact SHA-256 is recorded
in the delivery report after packaging.

## 0.2.1 correction evidence

The externally reported semantic gap is closed. Capability definitions own their valid action
vocabulary. Permission scopes can only narrow authority; they cannot create authority absent from
the capability definition. `finance.read + buy` is rejected as `ACTION_NOT_ALLOWED`, whereas the
valid pair `finance.execute + buy` remains denied by `FINANCIAL_EXECUTION_BLOCKED`.
