# Web client architecture

Phase 12 adds one browser interface to the certified Personal Assistant; it does not add a second
assistant or authority. The client is a React 19 single-page application built by Vite from strict
TypeScript. A minimal Node process serves immutable assets, emits public runtime configuration and
proxies only `/api/` and `/health/` to one server-configured backend origin. ADR-0013 records the
alternatives and boundary decision.

## Runtime boundaries

- Supabase Auth is the only authentication provider. The official public browser client receives
  only the project URL and anon/publishable key.
- The FastAPI backend remains authoritative for identity, device ownership, Conversation, Memory,
  AI Router, Orchestrator, Permissions, Risk, Confirmation, Task state, Safe Mode, audit and the
  financial hard deny.
- The Node process owns deployment destinations and transport headers, but makes no identity,
  permission, risk, Confirmation or business-rule decision.
- Browser-controlled identifiers and payloads are untrusted. Requests never carry a browser-picked
  user, provider, model, sensitivity, Safe Mode or permission decision.

## State and conversation flow

`SessionController` owns the finite authentication state and validates the Supabase subject against
`GET /api/v1/me` before rendering authenticated UI. `BackendClient` owns typed HTTP contracts,
timeouts, cancellation and classified errors. `ConversationController` owns the selected
conversation, in-flight logical send and idempotency identity. React components own only local view
and form state.

A new message gets one UUID. Double submit shares one in-flight promise; explicit transport retry
reuses that UUID; a new user intent gets a new UUID. Selecting another conversation increments an
epoch and aborts the old read, so a late response cannot render into the new conversation. The
backend response replaces the relevant server state; client cache is never authority.

## Truthful user experience

Assistant output is plain text. Server outcomes render as completed, permission required,
Confirmation required, denied, unsupported, failed or “Prepared — not executed.” Confirmation
buttons call the certified server routes and explicitly do not claim execution. Permissions are
read-only. Memory is created only from an explicit user form with `USER_EXPLICIT` provenance and
uses server archive/delete/version/Confirmation semantics.

Safe Mode cannot be changed in the client. There are no financial action controls, Executor,
browser microphone, Wake Word, Web Research or autonomous browsing paths.

## Offline, cache and multi-tab

The browser uses no service worker, durable queue or persistent server-state cache. Offline status
disables submission and preserves only the current in-memory draft. Reconnect permits a fresh,
explicit send; it does not flush hidden work. Read requests have one bounded retry for transient
transport failure; mutations never auto-retry.

Tokens, conversations, messages, Memory and permissions remain in memory. There is no use of
localStorage, sessionStorage or IndexedDB. A metadata-only `BroadcastChannel` carries logout events;
it never carries credentials or content. Logout/account switch cancels HTTP, clears session and
conversation state, and remounts the workspace under the verified user ID.

## Build and deployment assumptions

Node.js 24 and npm 11 install the exact lockfile. Production builds have no source maps and contain
no environment endpoint. At runtime, the server requires HTTPS public, backend and Supabase origins,
plus a public Supabase key. TLS termination must be configured before enabling HSTS. Phase 12
prepares this boundary but does not deploy or change any production service.

Known external gates are real Supabase authentication, TLS termination, proxy routing and
multi-browser behavior in staging. They do not weaken local certification and are marked
`REQUIRES STAGING`.
