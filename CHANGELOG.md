# Changelog

All notable changes to this project will be documented in this file.

## 0.13.0-web-research

- Added a server-authoritative, permission-gated Web Research path with bounded search,
  pinned-IP retrieval, redirect/DNS-rebinding defenses, untrusted-content isolation,
  grounded synthesis, and server-constructed citations.
- Added durable citation metadata and safe citation rendering in the Web client while
  preserving strict Android/KMP response compatibility.
- Research remains disabled and provider-unavailable by default until an operator supplies
  an approved provider configuration; no live credentials or deployments are included.

## 0.12.0-web-client

- Added a strict TypeScript/React web client with Supabase public-client authentication, in-memory
  sessions, typed certified-backend transport, conversations, truthful Assistant outcomes,
  explicit Memory controls, read-only permissions, and server-owned Confirmation controls.
- Added a minimal same-origin production server with fixed HTTPS upstreams, exact-origin mutation
  checks, restrictive CSP/security headers, bounded proxying, public runtime config, and no browser
  cookie or authorization authority.
- Added responsive system-theme UI, keyboard and screen-reader semantics, focus-managed dialogs,
  privacy-safe observability, honest offline behavior, and account/multi-tab cleanup without a
  durable browser queue.
- Added locked web dependencies, deterministic production build, CI gates, 90+ unit/integration/
  security/accessibility tests, and controlled Chromium E2E for create/send, Confirmation,
  reconnect, mobile navigation, and logout.
- Corrected native browser transport binding after E2E exposed an illegal `fetch` receiver; the
  client now binds the global fetch implementation once at construction.

## 0.11.1-offline-system-certification

- Corrected two KMP tests to return `Unit`, allowing JUnit discovery to execute the intended
  exception assertions instead of rejecting their signatures during initialization.
- Corrected the Gradle 8.9 wrapper distribution checksum to the verified official archive digest.
- Switched Room schema export to the official Room Gradle plugin and added the missing schema 2
  history, preventing concurrent variant processors from sharing an undeclared output file.
- Serialized KSP variant tasks and excluded KSP's transient `byRounds` shadow directory from Java
  compilation, preventing duplicate generated sources without reducing build-wide parallelism.
- Formatted the Phase 11 certification tests to satisfy the repository's enforced Ruff policy;
  product behavior, test strength, dependency authority, and delivery paths are unchanged.

## 0.11.0-offline-system

- Evolved the existing encrypted Room pending-operation record into an explicit durable state
  machine bound to the authoritative user and registered device, with authenticated payload
  integrity metadata and stable operation/idempotency identity.
- Added event-driven connectivity verification, atomic worker claims, controlled reconnect
  scheduling, process-death recovery, bounded classified retry with stable jitter, and
  server-idempotent reconciliation for response-loss ambiguity.
- Added truthful cached/pending/sync/ack/rejected/auth-required/cancellation UX, bounded caches and
  terminal retention, safe logout/account-switch/device-revocation handling, and a Room 1→2
  migration that fails closed for legacy unbound pending intent.
- Preserved one WorkManager delivery authority, current server revalidation, Voice and Wake privacy,
  Memory provenance, Safe Mode, financial hard deny, and the absence of any general Executor.
- Added focused Phase 11 state-machine, retry, identity, replay, migration, UX, and security tests;
  no backend migration, dependency, external-service change, production change, or secret was added.

## 0.10.1-wake-word-certification

- Replaced the inaccessible PackageManager permission-change API with the public AppOps
  `OPSTR_RECORD_AUDIO` listener, preserving event-driven revocation handling and lifecycle cleanup.
- Moved the intentionally synchronous activation replay record to the IO dispatcher and now fail
  closed when durable persistence fails before VoiceSession activation.
- Bound local HTTP/WebSocket transport to a flavor-owned BuildConfig capability that is false in
  staging and production, removing emulator endpoint authority and strings from the release APK.
- Updated Android and backend versions for the source correction discovered by the real API 35
  compilation gate.

## 0.10.0-wake-word

- Added a provider-independent Wake Word contract, explicit state machine, metadata-only events,
  bounded event age, debounce, and durable activation replay protection.
- Converged manual and wake activation through one controller before the existing Phase 9
  VoiceSession; no UI/detector/provider path or parallel Voice implementation exists.
- Added opt-in/privacy UI, JIT permission, a visible user-initiated microphone foreground service,
  and fail-closed lock-screen, power, thermal, permission, process-death, and reboot behavior.
- Added a fixed-frame local AudioRecord engine and replaceable detector boundary. No wake SDK,
  cloud STT fallback, provider credential, or unapproved model was added; production detection
  remains `REQUIRES MODEL TRAINING`.
- Added fake-engine end-to-end, authority, privacy, replay, lifecycle, manifest, migration-history,
  and Phase 0–10 regression coverage without backend schema or production changes.

## 0.9.0-realtime-voice

- Added scoped, expiring VoiceSession and idempotent VoiceTurn persistence.
- Added a bounded WebSocket protocol with partial/final transcript separation.
- Routed unknown microphone ingress through local CRITICAL-safe REALTIME policy.
- Bridged final voice turns into the certified Text Assistant and Orchestrator authority chain.
- Added Android JIT microphone capture, PCM playback, audio focus, barge-in, and bounded reconnect.
- Added a configurable calm/professional voice profile and deterministic fake realtime provider.
- Preserved no-Executor, financial hard-deny, Safe Mode, Confirmation, and no-Wake-Word boundaries.

## 0.8.1-android-agent-correction

- Removed direct UI network delivery and the unused bulk delivery entry point. Manual retry now
  re-enqueues the original durable operation through unique WorkManager work with `KEEP`.
- Preserved the original operation ID, idempotency key, payload, version, and bounded attempt state
  for every retry; WorkManager remains the only network-delivery caller.
- Restored the placeholder-only `.env.example` and added deterministic artifact packaging that
  preserves the template while excluding real environment files, secrets, caches, and outputs.
- Added delivery-path, concurrency, retry durability, and artifact-integrity regression tests.

## 0.8.0-android-agent

- Added a Kotlin Multiplatform contract/network module and native Android Compose application.
- Added Keystore-backed installation identity, device key pair, encrypted session material, and
  authenticated owner-safe Device registration.
- Added typed Text Assistant conversations, truthful outcome rendering, validated connectivity,
  encrypted Room cache, and bounded idempotent WorkManager delivery.
- Added local/staging/production flavors, debug/release boundaries, release TLS policy, Android
  security tests, documentation, and CI validation.
- Added no backend migration, Executor, voice, wake word, external side effect, financial action,
  provider secret, service-role key, or production change.

## 0.7.0-text-assistant

- Added durable owner-scoped conversations and messages with bounded context, deterministic
  sequencing, optimistic concurrency, semantic idempotency, and restrictive RLS foundations.
- Added the first controlled end-to-end text flow through MemoryService, AI Router, and the Phase 6
  Orchestrator, with centralized system instructions and truthful outcome semantics.
- Added explicit memory commands, sensitivity propagation, prompt-injection/financial guard
  regression tests, Phase 7 pgTAP definitions, documentation, and certification evidence.
- No Executor, live model credentials, or external side effects were introduced.

## 0.6.0-orchestrator

- Added a durable typed Orchestrator with a centralized lifecycle, optimistic concurrency,
  user-scoped idempotency, immutable plan fingerprints, and append-oriented transition evidence.
- Integrated owner-bounded MemoryContextPack selection, conservative sensitivity propagation,
  deterministic AI Router invocation, and strict structured proposal validation.
- Delegated all actionable work to TaskService and its certified Permissions, Risk, Confirmation,
  capability/action, device, and FinancialExecutionGuard chain.
- Added server-owned safe modes and an immutable future-executor envelope that grants no execution
  authority and is not exposed through public mutation APIs.
- Added pre-reevaluation plan-integrity rehashing so changed plan content cannot reuse an earlier
  confirmation, authorization evaluation, or future handoff.
- Added Alembic `0007_orchestrator`, restrictive RLS/pgTAP definitions, privacy-safe audit and
  observability hooks, security matrices, and full Phase 0–6 regression coverage.

## 0.5.0-ai-router

- Added a provider-independent protocol, immutable server-owned model catalog, canonical model
  classes/capabilities, and a disabled-by-default provider foundation.
- Added deterministic quality-first routing, explicit escalation, equivalent-quality fallbacks,
  classified failures, bounded retries, provider health, and no silent quality degradation.
- Added fail-closed PUBLIC/INTERNAL/PRIVATE/SENSITIVE/CRITICAL routing with MemoryContextPack
  sensitivity propagation, context/output bounds, and no Router-side truncation.
- Added versioned cost metadata, deterministic estimates, soft/hard request/daily/monthly budget
  foundations, privacy-safe usage accounting, and OpenTelemetry-ready observer events.
- Added Alembic `0006_ai_router`, owner-scoped RLS/pgTAP definitions, security audit integration,
  and routing/security/regression matrices without live provider calls or credentials.

## 0.4.0-memory

- Added classified owner-scoped MemoryRecord, privacy-scrubbable MemoryRevision, and append-oriented
  MemoryEvent models with Alembic `0005_memory_core`.
- Added explicit provenance, sensitivity, bounded confidence/importance, deterministic exact
  deduplication, optimistic mutation, archive, lazy expiration, and no-restore privacy deletion.
- Added permission/risk/confirmation/audit integration through server-owned `memory.read`,
  `memory.write`, and `memory.delete` action vocabularies.
- Added bounded retrieval, explicit archived/expired queries, deterministic context packs, RLS,
  pgTAP staging evidence, and Memory security/concurrency/regression matrices.
- Deferred physical vectors and embedding generation until a provider/model can define a valid
  dimension; no AI or external service was added.

## 0.3.0-task-engine

- Added Task, TaskAttempt, and append-oriented TaskEvent models with Alembic `0004`.
- Added a centralized canonical state machine with terminal-state protection.
- Added user-scoped idempotency, request fingerprints, and optimistic version updates.
- Added authorization-derived initial states, hard-deny handling, cancellation, expiration, and
  internal claim/completion/failure/reevaluation foundations without an Executor.
- Added owner-scoped Task APIs, security-relevant audit events, restrictive RLS, staging pgTAP,
  and lifecycle/security matrices.

## 0.2.1-capability-action-boundary

- Added server-owned `Capability.allowed_actions` as the authoritative action vocabulary.
- Rejected unsupported operations at permission grant with `ACTION_NOT_ALLOWED`.
- Added authorization-time defense against invalid proposals and malformed legacy permissions.
- Ensured invalid actions are rejected before risk classification.
- Preserved the independent, non-overridable financial execution guard.
- Added incremental Alembic migration `0003_capability_actions` and explicit security matrices.

## 0.2.0-permissions-risk-audit

- Added structured capability, permission, authorization-decision, confirmation, and audit models.
- Added default-deny capability-plus-scope and device-scoped authorization.
- Added deterministic risk classification and confirmation policies.
- Added an absolute Phase 2 financial-execution guard.
- Added AAL2 own-account permission administration without a privileged-user bypass.
- Added append-oriented, owner-isolated, secret-redacted audit evidence.
- Added Alembic `0002`, Phase 2 RLS definitions, and a staging pgTAP suite.
- Added permission, confirmation, financial, audit, IDOR, escalation, migration, and regression
  tests.

## 0.1.0-identity-auth

- Added strict Supabase JWT verification using cached asymmetric JWKS keys.
- Added JIT user provisioning and immutable request identity context.
- Added user, device, and observed authentication-session SQLAlchemy models.
- Added idempotent owned-device registration, listing, and revocation APIs.
- Added Alembic migrations, PostgreSQL RLS definitions, and staging pgTAP validation.
- Added MFA assurance-level representation without implementing MFA policy.
- Added authentication, ownership, migration, constraint, and security regression tests.

## 0.0.1-foundation

- Added the initial monorepo and modular-monolith directory structure.
- Added a minimal FastAPI backend with validated settings and health endpoints.
- Added structured JSON logging and foundational secret redaction.
- Added real foundation tests and automated quality checks for pull requests.
- Added Railway, Supabase, security, contribution, architecture, and decision documentation.
