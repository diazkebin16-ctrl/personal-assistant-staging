# Phase 12 — Web Client certification

PHASE: **PHASE 12 — WEB CLIENT**  
STATUS: **PASS**

BASE ARTIFACT: `personal-assistant-0.11.1-offline-system-certified.zip`  
BASE SHA-256: `8e223a934c72d4c4425a92a2cead939543b9ddc75683947a4825044526f06817`  
BASE SHA VERIFIED: **YES, before extraction or source changes**

## Implemented architecture and experience

IMPLEMENTED: A responsive authenticated browser client for the canonical Personal Assistant
backend: sign-in/out, session validation, conversation list/create/open, text chat, truthful outcome
states, explicit Memory list/create/archive/delete, read-only permission state, server-issued
confirmation decisions, offline/degraded presentation, theme support, accessibility foundations,
same-origin production API proxy, and privacy-safe operational observation.

WEB STACK: React 19.2.8, TypeScript 6.0.3 in strict mode, Vite 8.2.2, Vitest 4.1.11,
Playwright 1.62.1, official Supabase JavaScript client 2.114.0, and a minimal Node production
server. The certified runner used Node 24.19.0.  
ARCHITECTURE: The browser is presentation only. The Node boundary serves immutable static assets,
an allowlisted public runtime config, and a same-origin `/api` proxy. The existing backend remains
the only authority for identity, permissions, confirmation, risk, Safe Mode, orchestration,
Memory, tasks, and outcomes. ADR-0013 records the selection and rejected alternatives.  
AUTH: Official least-privilege Supabase public-client authentication; public anon/publishable keys
only. The returned subject is checked against canonical backend `/me`. No browser-supplied
`user_id` is sent or trusted.  
SESSION STORAGE: Access and refresh material remain in memory (`persistSession: false`). Supabase
auto-refresh is enabled for that in-memory session. No token, Authorization header, conversation,
or Memory content is persisted in browser storage.  
API CLIENT: Typed request/response contracts, 15-second timeout, cancellation, bounded read retry,
classified errors, no credential forwarding, and stable UUID idempotency per logical message.
Mutations are never blindly retried.  
CONVERSATIONS: Bounded server-backed listing, create/open, bounded message load, and canonical text
send. Browser state is disposable and never becomes conversation authority.  
CHAT UI: Semantic user/assistant messages, sending/waiting state, classified failures, permission,
confirmation, denied, unsupported, Safe Mode, offline, and future-execution-only truth states.  
MEMORY UI: Explicit user-directed list/create/archive/delete only. Deletes preserve backend version
and server confirmation identity. No inferred or automatic client-side Memory exists.  
PERMISSION UI: Read-only rendering of backend grants, scope, expiry, and confirmation policy. It
does not use browser permission APIs or grant Assistant permissions.  
CONFIRMATION UI: Approve/reject calls use only a server-issued confirmation identifier. The UI
states explicitly that confirmation is not execution and cannot bypass authorization.  
SAFE MODE: Server-owned and rendered fail-closed. The client has no Safe Mode override field or
control.  
FINANCIAL BOUNDARY: FinancialExecutionGuard remains backend-owned. No buy, sell, transfer,
withdraw, deposit, order, leverage, or risk-increase action control or delivery path was added.  
OFFLINE / DEGRADED UX: Connectivity loss blocks sends, preserves only the in-memory draft, renders
an explicit offline state, and never fabricates a response or server acknowledgement. Reconnect
retry uses the original logical idempotency key. No second durable Offline System was created.  
STATE MANAGEMENT: Small typed controllers separate session and conversation server state from
React-local UI state. Request generation plus cancellation prevents late Conversation A responses
from entering Conversation B.  
CACHE: Runtime configuration, HTML, and API data are `no-store`; hashed static assets are immutable.
No sensitive application cache or service worker exists. The backend remains source of truth.  
BROWSER STORAGE: None used by application code for auth, content, Memory, authority, or drafts.  
MULTI-TAB: `BroadcastChannel` propagates logout. Each tab remains independently server-validated;
no tab can grant authority or fabricate confirmation state.  
LOGOUT: Clears the in-memory session, conversation, Memory/permission UI state, aborts in-flight
backend calls, and broadcasts cleanup to other tabs even if remote sign-out fails.  
SESSION EXPIRY: A 401 expires once, cancels/clears account-bound state, and returns to re-auth UX;
there is no 401 retry loop. Account switching cannot inherit the previous account cache.  
XSS PROTECTION: Assistant text is rendered as React text only. No raw HTML/Markdown renderer,
dangerous HTML sink, executable link, remote script, or untrusted navigation path exists. XSS and
HTML-injection payload tests render inert.  
CSRF PROTECTION: Browser bearer requests omit cookies and credentials. The same-origin production
proxy independently requires exact trusted `Origin` for mutations and returns 403 otherwise.  
CONTENT SECURITY POLICY: Production policy uses self-only scripts/styles, explicit Supabase HTTPS
connect origin, `object-src 'none'`, `frame-ancestors 'none'`, `worker-src 'none'`, and no
`unsafe-inline`/`unsafe-eval`. Development uses only the pinned React preamble hash plus loopback
HMR endpoints.  
SECURITY HEADERS: CSP, COOP, CORP, Origin-Agent-Cluster, no-referrer, nosniff, DENY framing, and a
deny-by-default Permissions-Policy. HSTS emission is conditional on confirmed TLS termination and
was locally validated; deployed HSTS still requires staging TLS verification.  
HTTPS / NETWORK SECURITY: Production origins are server-controlled HTTPS origins without
credentials, path, query, or fragment. Client runtime config accepts only `/api/v1`, HTTPS
Supabase, a public key, and build version 0.12.0. No production cleartext or TLS bypass exists.  
ACCESSIBILITY: Semantic landmarks and labels, live status announcements, visible focus, keyboard
send, focus-trapped/restored dialogs, escape handling, and automated axe checks.  
RESPONSIVE DESIGN: One adaptive application for desktop/tablet/mobile; narrow navigation exposes
Chat, Memory, and Permissions as keyboard-accessible tabs. Light, dark, and system themes use
central design tokens.  
PRIVACY: No trackers, advertising, session replay, third-party fonts, content analytics, or remote
arbitrary JavaScript. External requests are limited to the configured Supabase auth origin and the
same-origin canonical API.  
OBSERVABILITY: An interface permits only request ID, conversation ID, route, latency, category,
retry count, and build version. Raw conversation/Memory content, tokens, credentials, headers, and
sensitive payloads are structurally excluded.

## Source inventory

FILES CREATED:

- Complete `apps/web` source, tests, server, lockfile, safe environment examples, and tool configs
  (46 files).
- `docs/architecture/web-client.md`
- `docs/architecture/web-dependencies.md`
- `docs/decisions/ADR-0013-web-client-boundary.md`
- `docs/operations/web-client-deployment.md`
- `docs/security/web-client.md`
- `docs/certification/phase12-web-client.md`

FILES MODIFIED:

- `.env.example`, `.github/dependabot.yml`, `.github/workflows/ci.yml`, `.gitignore`
- `CHANGELOG.md`, `README.md`, `pyproject.toml`, `uv.lock`
- `backend/app/core/config.py`, `mobile/androidApp/build.gradle.kts`
- `scripts/package_release.py`
- Version/packaging boundary assertions in
  `tests/integration/test_android_agent_contract.py`,
  `tests/integration/test_offline_system_contract.py`,
  `tests/integration/test_wake_word_contract.py`,
  `tests/security/test_offline_system_security.py`,
  `tests/unit/test_application.py`, and `tests/unit/test_release_packaging.py`

FILES DELETED: `apps/web/.gitkeep` only.  
DEPENDENCIES ADDED: The exact direct/transitive graph is locked in `apps/web/package-lock.json`.
Purpose, need, alternatives, licenses, maintenance/security assessment, and measured bundle impact
for every direct dependency group are recorded in `docs/architecture/web-dependencies.md`. License
inventory covered 249 installed unique dependencies with no missing metadata.  
MIGRATIONS: None. Backend migrations `0001`–`0009` remain byte-identical to the certified baseline;
no `0010` exists. Room schema history 1 and 2 is unchanged.

## Certification gates

WEB UNIT TESTS: **PASS — 69/69**  
WEB INTEGRATION TESTS: **PASS — 4/4**  
WEB E2E TESTS: **PASS — 5/5 controlled Chromium flows** (auth/chat, confirmation without
execution, offline/reconnect exactly once, mobile navigation, logout)  
WEB SECURITY TESTS: **PASS — 15/15**  
ACCESSIBILITY TESTS: **PASS — 4/4 automated DOM/axe checks**  
WEB AGGREGATE: **PASS — 92/92 Vitest plus 5/5 Playwright**

FORMAT: **PASS — Prettier; Ruff 261 files**  
LINT: **PASS — ESLint zero warnings; Ruff zero findings**  
TYPECHECK: **PASS — TypeScript strict; mypy 187 source files**  
PRODUCTION BUILD: **PASS — 75 modules; JS 433.14 KiB raw / 123.34 KiB gzip; CSS 11.59 KiB raw /
3.47 KiB gzip; no sourcemaps**  
BUNDLE SECRET SCAN: **PASS — no credential/JWT/private-key signature, configured local/test
endpoint, source secret, or test provider; no populated environment file packaged**  
DEPENDENCY AUDIT: **PASS — npm audit 0 vulnerabilities; pip-audit 0 known vulnerabilities;
npm graph valid; pip check valid; 249-dependency license inventory complete**  
CSP / HEADER VALIDATION: **PASS — runtime header assertions, public-config allowlist, and cross-origin
mutation 403 verified**

BACKEND REGRESSION: **PASS — 860/860**  
PHASE 7–11 REGRESSION: **PASS — included in full backend/security and required mobile/KMP gates;
no certified authority/delivery path changed**  
MIGRATION VALIDATION: **PASS — fresh upgrade, every supported downgrade/re-upgrade boundary,
autogenerate drift check, and no new upgrade operations; 0001–0009 byte-identical**

Additional mobile gates:

- KMP/JVM plus Android local unit: **PASS — 195/195, 0 failed/errors/skipped**.
- Android lint: **PASS — zero issues with warnings-as-errors**.
- Clean local debug: **PASS — 60 tasks**; APK integrity/version/secret scan passed.
- Clean production release: **PASS — 88 tasks**; R8/resource shrinking and APK integrity passed.
- Merged production manifest: **PASS**; backup false, cleartext false, explicit exported state.
- Release network security: **PASS**; cleartext false, system trust anchors only.
- Release APK scan: **PASS**; no credential signature, emulator/loopback endpoint, or cleartext URL.
- Room schema 1 SHA-256:
  `3e2a72a376cccc05653250ce33cd4f09b555468cc1ce6f73fc739f046a19d159`.
- Room schema 2 SHA-256:
  `2a31381d3fa64fec83fd59b928a61ab00d7f68e9b5304e849a438d528160a828`.

PATCH / TECHNICAL DEBT REVIEW: **PASS**. A native-fetch receiver defect found by E2E was fixed at
the transport boundary with a focused regression. Safe web environment examples were initially
excluded by an over-broad package predicate; the root predicate now uses an exact allowlist with
focused regression. A historical white-box assertion was replaced with the same functional
packaging contract. No bypass, weakened security rule, duplicated authority, duplicated delivery
path, dependency patch, or unresolved technical-debt workaround remains.

SECURITY: **PASS**  
CRITICAL: **0**  
HIGH: **0**  
MEDIUM: **0**  
LOW: **0**

## External boundaries and release

KNOWN LIMITATIONS: Phase 12 intentionally has no durable browser offline queue, service worker,
browser voice/wake capability, Web Research, Executor, financial execution, or client-side
authority. The E2E certification uses controlled fake auth/backend services and no production
credentials. Physical Android runtime validations from Phase 11 remain external.  
STAGING REQUIREMENTS: Live Supabase sign-in/refresh/revocation and RLS/JWT/JWKS behavior; deployed
backend proxy, TLS termination and HSTS; multi-tab behavior across the deployed origin; production
CSP against the chosen Supabase project; PostgreSQL concurrency; and end-to-end permission,
confirmation, Safe Mode, and response-loss behavior.  
RUNTIME REQUIREMENTS: Node.js 22.12 or newer; HTTPS termination; fixed `WEB_PUBLIC_ORIGIN`,
`WEB_BACKEND_ORIGIN`, `WEB_SUPABASE_URL`, and public `WEB_SUPABASE_ANON_KEY`; canonical Phase 11+
backend; `npm ci` followed by `npm run build`; no user-editable backend destination.  
EXTERNAL SERVICES MODIFIED: **None**  
PRODUCTION MODIFICATIONS: **None**  
SECRETS ADDED: **None**

FINAL ARTIFACT: `personal-assistant-0.12.0-web-client.zip`  
FINAL SHA-256: Published in the external certification report beside the ZIP; a ZIP cannot contain
its own digest without changing that digest.  
DETERMINISTIC PACKAGING: **PASS — two independent emissions are byte-identical**

NEXT PHASE: **PHASE 13 — NOT STARTED**

## Declaration

**PHASE 12 = COMPLETE**
