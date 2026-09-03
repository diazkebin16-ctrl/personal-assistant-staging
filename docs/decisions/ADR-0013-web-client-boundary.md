# ADR-0013: Web client boundary

Status: accepted for Phase 12

## Context

The certified backend already exposes owner-scoped Identity, Conversation, Text Assistant, Memory,
Permissions, Confirmation, Task, and Orchestrator APIs. Authentication is Supabase-issued JWT
verification; the backend has no password endpoint and must not gain a parallel login authority.
The browser is untrusted and Phase 12 must not duplicate Android's durable Offline System.

## Options considered

1. A Next.js application with cookie sessions and server actions. This supplies a large
   server-rendering surface that Phase 12 does not need and would require a new session authority,
   CSRF lifecycle, and token handoff design.
2. A React/Vite browser client calling a separately hosted backend. This is small, but requires new
   CORS policy and exposes a configurable backend destination to browser code.
3. A React/Vite browser client served by a minimal Node process that proxies only the certified API
   paths on the same origin. Supabase Auth remains the identity provider, bearer tokens remain in
   memory, and the proxy performs no authorization or business-rule decisions.

## Decision

Use option 3. React provides accessible component composition; TypeScript strict mode provides
contract checking; Vite provides a small deterministic production build; Vitest/Testing Library
provide component and integration validation; Playwright provides controlled browser E2E. The
official Supabase JavaScript client is the only auth implementation.

The production server exposes public runtime configuration, applies security headers, and proxies
`/api/` and `/health/` to one server-controlled HTTPS backend origin. It never persists tokens,
never converts cookies into credentials, never evaluates permissions, and never changes backend
responses. Mutation requests must come from the configured same origin. The browser sends the
Supabase access token explicitly and keeps it only in memory (`persistSession: false`).

The local Vite policy additionally permits loopback-only WebSocket connections for hot module
reload. That development-only source is absent from the production CSP.

Assistant output is rendered as plain text. Phase 12 intentionally adds no Markdown/HTML renderer,
service worker, persistent server-state cache, client permission engine, Executor, Voice/Wake
feature, or Web Research capability.

Accessibility is tested with axe-core, semantic DOM assertions, keyboard/focus tests, and browser
E2E. `eslint-plugin-jsx-a11y` was evaluated but rejected because its current peer range requires an
unsupported ESLint major; pinning an obsolete linter or bypassing peer resolution would create
avoidable supply-chain debt.

## Consequences

- Production deployment must provide four runtime values: the public web origin, the HTTPS backend
  origin, the HTTPS Supabase origin, and the public Supabase anon/publishable key.
- Page reload requires reauthentication. This is the deliberate security tradeoff for not placing
  bearer or refresh tokens in browser persistence.
- Logout and session-expiry events clear all in-memory user state and broadcast a metadata-only
  logout signal to other tabs.
- Real Supabase, TLS termination, and cross-tab browser behavior remain staging/runtime gates.
