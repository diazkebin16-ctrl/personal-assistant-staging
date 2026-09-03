# Web client security and privacy

## Threat model

The browser, DOM, URL, API payloads and user-visible identifiers are untrusted. A bearer token proves
only the Supabase session; the backend derives the owner and re-evaluates all authorization, risk,
Confirmation, Safe Mode and financial policy. The web server forwards a small header allowlist and
never creates cookies or authorization evidence.

## Authentication and storage

The Supabase client uses PKCE, automatic refresh, disabled URL-session detection and
`persistSession: false`. Access and refresh tokens are held only inside process memory. They are not
logged, placed in cookies, localStorage, sessionStorage or IndexedDB, and disappear on reload,
logout, account switch or process exit. The deliberate consequence is reauthentication after page
reload. A 401 expires local state once and is never retried indefinitely.

## XSS, injection and navigation

React text nodes render all assistant, conversation and Memory content; no raw HTML, Markdown,
dynamic script, `dangerouslySetInnerHTML` or user-controlled navigation exists. Consequently HTML,
script and `javascript:` payloads stay inert text. Runtime config rejects unknown fields, credentialed
URLs, paths, queries, fragments, cleartext production origins and service-role keys. The static
server resolves paths under one fixed build root and blocks traversal.

## CSRF and network controls

Backend authentication is an explicit Authorization bearer header with `credentials: omit`, not an
ambient cookie, so classic cookie CSRF does not grant authority. The same-origin proxy additionally
rejects every mutation without an exact configured `Origin`. Production accepts only fixed HTTPS
origins, follows no redirects, bounds request bodies to 1 MiB and upstream calls to 20 seconds, and
forwards only Authorization, Content-Type and request ID.

Production CSP uses self-only default/script/style sources, exact Supabase connectivity, no base,
object, frame ancestor or worker, and `upgrade-insecure-requests`; it contains no unsafe-inline,
unsafe-eval or wildcard. Development adds only a hash for Vite's pinned React preamble and
loopback-only HMR WebSockets. Other headers include no-referrer, nosniff, DENY framing,
same-origin opener/resource policies, origin isolation, a disabled microphone/camera/geolocation/
payment/USB policy, and optional HSTS after confirmed TLS termination.

## Privacy and observability

No advertising, session replay, analytics SDK, third-party font or remote script exists. System
fonts and local assets avoid tracking. Observations contain request ID, route, conversation ID,
latency, status category, retry count and build version only. They exclude messages, Memory,
credentials, tokens, headers and response bodies.

## Authority exclusions

The client cannot force provider/model, lower sensitivity, override Safe Mode, grant Assistant
permissions, fabricate Confirmation, execute a Task or perform financial actions. Voice, Wake Word,
Web Research and a general Executor remain absent. Security tests and bundle scans enforce these
properties.
