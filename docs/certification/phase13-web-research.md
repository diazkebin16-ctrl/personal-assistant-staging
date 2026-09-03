# Phase 13 — Web Research certification

PHASE: **PHASE 13 — WEB RESEARCH**  
STATUS: **PASS**

BASE ARTIFACT: `personal-assistant-0.12.0-web-client.zip`  
BASE SHA-256: `1715f9f04f49984a26373281eb0c68e1d0616de0c6cd22e090e9d60401f4d127`  
BASE SHA VERIFIED: **YES, before extraction or source changes**

## Implemented architecture

IMPLEMENTED: A bounded, fail-closed Web Research capability integrated into the canonical text
assistant path. The server, not the browser or model, selects `NO_RESEARCH`, `SEARCH`, `FETCH`, or
`MULTI_SOURCE_RESEARCH`; authorizes `web.research`; minimizes outbound queries; retrieves and
extracts untrusted evidence; requests structured synthesis through the existing AI Router; and
validates citations before returning and persisting the response.

AUTHORITY PATH: Text Assistant → Orchestrator → research policy and existing PermissionsEngine →
search/retrieval provider → untrusted evidence → existing AI Router → server-side citation
validation → Text Assistant. No second assistant, orchestration authority, task engine, executor,
confirmation system, Memory system, or delivery path was added.  
SERVER-OWNED MODE: Client requests contain no research mode, provider choice, URL allow decision,
or authority override. Research is disabled by default and requires server configuration plus an
authorized `web.research` action.  
POLICY: Sensitive and critical requests are rejected before outbound activity. Search terms are
bounded, normalized, minimized, and redacted. Conversation history and Memory are never supplied
to the search provider. Policy denials use the existing security-audit path and reveal no secret
material.  
URL SAFETY: Only canonical HTTP(S) URLs without credentials or unsafe ports are accepted. Every
resolved address must be globally routable. Loopback, private, link-local, carrier-grade NAT,
documentation, multicast, reserved, unspecified, IPv4-mapped, and local/internal hosts are
rejected. Every redirect is recanonicalized and re-resolved to prevent DNS rebinding and redirect
pivots.  
RETRIEVAL: The standard-library transport connects to a validated pinned IP while preserving the
original HTTPS hostname for TLS SNI and certificate verification. Per-request and total time,
redirect, source, byte, and search-attempt budgets are enforced. Only identity content encoding
and bounded HTML/plain-text content are accepted.  
EXTRACTION: Scripts, styles, templates, SVG/canvas content, comments, accessibility-hidden nodes,
and display-hidden content are removed before normalization and truncation. Extracted content is
always labeled and handled as untrusted evidence, never as instructions.  
PROVIDERS: Search uses an explicit provider abstraction. The fake provider is test-only and the
registry rejects it in production. No live provider is selected or enabled in the certified
artifact.  
SYNTHESIS: The existing AI Router receives a structured request with tools disabled and a strict
separation between user request and untrusted evidence. The model can reference only evidence
identifiers; it cannot supply final URLs. The server maps identifiers to canonical sources and
rejects unknown, missing, duplicated, unsafe, or lexically unsupported citations.  
CACHE: A bounded, TTL-limited cache uses SHA-derived keys. It cannot bypass authorization,
sensitivity policy, URL validation, evidence validation, or source limits.  
OBSERVABILITY: Metrics and logs are limited to classifications, counts, durations, result states,
and correlation identifiers. Queries, page content, credentials, headers, tokens, and model
evidence are excluded.  
TEXT ASSISTANT: Research intent/outcomes and validated citations extend the existing canonical
message contract. Citations are persisted with each assistant message and returned through the
same API path.  
WEB CLIENT: Citations use a strict typed contract and are rendered as React text plus external
HTTPS links with `target="_blank"` and `rel="noopener noreferrer"`. Script, credential-bearing,
local, private, and otherwise unsafe links are suppressed. No raw HTML or research engine exists
in the browser.  
KMP/ANDROID: The shared response contract accepts validated citation metadata with backward-safe
empty defaults and a display-safety helper. Mobile remains a presentation client and has no
provider, fetcher, mode selector, or research authority.  
FINANCIAL BOUNDARY: No buy, sell, transfer, withdrawal, deposit, order, leverage, risk-increasing,
or financial execution capability was added. The existing FinancialExecutionGuard remains the
authority.

## Source inventory and data model

FILES CREATED: 24, including the complete `backend/app/research` boundary, focused unit,
integration, security, web, and KMP tests, migration `0010_web_research.py`, ADR-0014, architecture,
security, operations, and this certification document.  
FILES MODIFIED: 41, limited to canonical route/contract integration, versioning, documentation,
configuration, test fixtures, migration expectations, web citation rendering, and KMP response
presentation.  
FILES DELETED: 0.  
VERSION: `0.13.0`; Android `versionCode` 130000.  
DEPENDENCIES ADDED: **None**. Retrieval uses the standard library and the existing locked graphs.  
MIGRATION: `0010_web_research.py` adds bounded citation JSON with an empty-list default, extends
the truthful assistant outcome constraint, and registers the `web.research` capability. The
migration has a complete downgrade and re-upgrade path. Migrations `0001`–`0009` remain
byte-identical to the certified Phase 12 baseline.  
ROOM: No Room migration or schema change. Schema history 1 and 2 remains byte-identical.

## Certification gates

PHASE 13 FOCUSED BACKEND: **PASS — 138/138**  
BACKEND FULL REGRESSION: **PASS — 998/998**  
BACKEND SECURITY: **PASS — 377/377**  
PHASE 8 REGRESSION: **PASS — 76/76**  
PHASE 9 REGRESSION: **PASS — 58/58**  
PHASE 10 REGRESSION: **PASS — 53/53**  
PHASE 11 REGRESSION: **PASS — 79/79**  
FORMAT: **PASS — Ruff 283 files; Prettier**  
LINT: **PASS — Ruff and ESLint, zero findings/warnings**  
TYPECHECK: **PASS — mypy strict 204 source files; TypeScript strict**  
PYTHON COMPILE: **PASS**

WEB TESTS: **PASS — 114/114 Vitest**  
WEB E2E: **PASS — 5/5 Playwright**  
WEB PRODUCTION BUILD: **PASS — 75 modules; JS 434.30 KiB raw / 123.79 KiB gzip; CSS 11.82 KiB
raw / 3.52 KiB gzip**  
KMP/JVM: **PASS — 146/146, 0 failed/errors/skipped**  
ANDROID UNIT: **PASS — 55/55, 0 failed/errors/skipped**  
ANDROID LINT: **PASS — zero issues with warnings-as-errors**  
CLEAN LOCAL DEBUG: **PASS — 57 tasks**  
CLEAN PRODUCTION RELEASE: **PASS — 85 tasks; R8 and resource shrinking enabled**

MIGRATION VALIDATION: **PASS — fresh upgrade, all supported downgrade/re-upgrade boundaries,
autogenerate drift check, and no unexpected upgrade operations**  
MERGED PRODUCTION MANIFEST: **PASS — cleartext false, backup false, network-security configuration,
and explicit exported state**  
RELEASE NETWORK SECURITY: **PASS — system trust anchors only; no cleartext or TLS bypass**  
RELEASE APK INTEGRITY: **PASS — unsigned release APK, as expected without a release signing key;
ZIP alignment valid; version 0.13.0/code 130000/target 35**  
RELEASE APK SHA-256:
`6daa27854f51bc9b46f6cae965bd3021b3ec4cd3ef4d1e52ef95933b901d3bc2`  
APK/SOURCE SECRET AND ENDPOINT SCAN: **PASS — no credential signature, private key, JWT, populated
secret, configured loopback/emulator endpoint, production cleartext endpoint, or test provider**  
DEPENDENCY VALIDATION: **PASS — npm graph valid; npm audit 0 vulnerabilities; pip graph compatible;
pip-audit 0 known vulnerabilities; locked Gradle production and desktop-test graphs resolve
offline**

ROOM SCHEMA 1 SHA-256:
`3e2a72a376cccc05653250ce33cd4f09b555468cc1ce6f73fc739f046a19d159`  
ROOM SCHEMA 2 SHA-256:
`2a31381d3fa64fec83fd59b928a61ab00d7f68e9b5304e849a438d528160a828`  
GRADLE LOCK SHA-256 — settings:
`e58bb2ed80db9f829601a658d7c33b9802eb7d2191c31e79c28e01f14c225926`  
GRADLE LOCK SHA-256 — Android app:
`9b518889a0825cd9f501b4c10c41869b289b9b810c9753b2b7c5fbf6fb63f396`  
GRADLE LOCK SHA-256 — shared:
`1157285820a01f647696d435b058d8771a905ff19dd89c1f57bcf706bb580543`

PATCH / TECHNICAL DEBT REVIEW: **PASS**. Defects found during focused certification were corrected
at their owning boundaries and covered by focused plus full relevant regression. An interrupted
release-build result was not counted; a clean rerun completed successfully. An initial combined
clean/debug runner collision was isolated to held generated output; clean and debug were rerun as
separate verified gates without source changes. No patch dependency, bypass, weakened test,
duplicated authority, duplicated delivery path, or unresolved workaround remains.

SECURITY: **PASS**  
CRITICAL: **0**  
HIGH: **0**  
MEDIUM: **0**  
LOW: **0**

## External boundaries and release

KNOWN LIMITATIONS: The certified tests use controlled fake search, DNS, transport, auth, backend,
and AI Router boundaries. No live search provider, public Internet page, production credential,
paid model request, production deployment, or external service mutation was used. Android physical
runtime validation remains external.  
REQUIRES REAL PROVIDER TEST: Provider credentials, quota/error behavior, live result quality,
robots/legal policy, public DNS behavior, TLS/certificate behavior, and provider-specific abuse
controls must be validated in staging before enabling research.  
STAGING REQUIREMENTS: Live search provider; representative public HTTPS sources and redirects;
DNS rebinding and egress controls at the deployment network; PostgreSQL migration/concurrency;
live AI Router structured output; deployed browser CSP/proxy/TLS; operational metrics and alerting;
and Android device rendering of citations.  
RUNTIME REQUIREMENTS: Research remains disabled unless the operator configures a non-test provider
and explicitly enables it. Egress controls must independently deny private/internal networks.
Existing identity, PermissionsEngine, AI Router, Text Assistant, database, and audit dependencies
remain mandatory.  
EXTERNAL SERVICES MODIFIED: **None**  
PRODUCTION MODIFICATIONS: **None**  
SECRETS ADDED: **None**

FINAL ARTIFACT: `personal-assistant-0.13.0-web-research.zip`  
FINAL SHA-256: Published in the external certification report beside the ZIP; a ZIP cannot contain
its own digest without changing that digest.  
DETERMINISTIC PACKAGING: **PASS — two independent emissions are byte-identical**

NEXT PHASE: **PHASE 14 — NOT STARTED**

## Declaration

**PHASE 13 = COMPLETE**
