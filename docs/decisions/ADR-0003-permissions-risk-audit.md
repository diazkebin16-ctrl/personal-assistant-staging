# ADR-0003: Permissions, Risk, Confirmation, and Audit Core

## Decision

Adopt a default-deny authority pipeline that separates verified identity, explicit permission,
deterministic risk, global safety guards, human confirmation, immutable decision, and audit
evidence.

- An LLM is only a proposer and has no grant, risk, confirmation, or execution authority.
- Permissions bind a capability to structured scope and optional device.
- Capabilities own a persisted server-defined action vocabulary; permission scope may narrow but
  never extend that vocabulary.
- Risk is calculated independently from server-owned capability attributes.
- Confirmations are user/action/scope-bound, expiring, and replay-protected.
- Financial execution is denied unconditionally in Phase 2.
- Audit is append-oriented and required in the same transaction for security-relevant decisions
  and mutations.
- AAL2 own-account administration solves bootstrap without a general authorization bypass.
- Unestablished safety or auditability fails closed.

## Rationale

This keeps authority deterministic, testable, and independent of future probabilistic models. It
preserves human control, supports multiple devices and temporary grants, prevents permission
self-escalation, and creates evidence before a future executor is introduced.

## Consequences

Phase 2 can decide but cannot execute. PostgreSQL RLS is defense in depth and still requires
runtime validation in Supabase staging. Task orchestration and side effects remain Phase 3 or
later concerns.

The incremental `0003_capability_actions` migration adds and populates the catalog vocabulary
without rewriting certified Phase 2 history. Grant and authorization boundaries use the same
`Capability` membership rule. Invalid pairs are denied before risk classification, while the
financial guard continues to apply independently to valid financial-execution pairs.
