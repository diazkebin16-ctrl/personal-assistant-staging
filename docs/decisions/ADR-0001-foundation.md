# ADR-0001: Foundation architecture

- Status: Accepted
- Date: 2026-09-01

## Decision

Use a monorepo containing a modular monolith, with Python/FastAPI for the backend, GitHub pull
request CI, Railway-ready deployment, and Supabase-ready persistence. Keep environments separate
and all external integrations optional and dormant until an approved phase implements them.

## Rationale

This provides operational simplicity, low maintenance, and room for future scaling while avoiding
premature distributed-system complexity. It preserves the approved providers and creates clear
module boundaries without microservices or speculative interfaces.

## Consequences

The initial backend can run without cloud credentials. Future persistence, auth, observability,
and device functionality must extend the existing boundaries and receive phase-specific approval.
