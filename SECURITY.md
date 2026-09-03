# Security Policy

## Foundation rules

- Never commit secrets, credentials, tokens, private keys, or populated `.env` files.
- Keep local, staging, and production environments separate.
- Apply least privilege to every future identity, device, service, and integration.
- Protect future sensitive operations with explicit, auditable permissions.
- Never perform an automatic financial action without the user's explicit authorization and the
  approved safeguards.

The repository includes basic log redaction as defense in depth. It does not replace correct
secret storage or access control.

Conversation history is private owner-scoped data. Raw messages, prompts, Memory context, and model
responses must not enter operational logs, traces, Audit metadata, or AI usage telemetry. A
conversation or model response never grants permission, changes risk, satisfies confirmation,
selects a provider/model, lowers sensitivity, or authorizes execution.

## Authentication foundation

- Supabase Auth is the only authentication authority.
- The backend accepts only signature-verified asymmetric `ES256` or `RS256` user tokens.
- Issuer, audience, expiry, required claims, token type, and algorithm are validated.
- Access tokens, refresh tokens, authorization headers, JWTs, passwords, private keys, and service
  role keys must never be logged or returned.
- `SUPABASE_SERVICE_ROLE_KEY` remains optional, server-only, and unused in Phase 1.
- Test authentication exists only through FastAPI dependency overrides in test code.

RLS is defense in depth for direct Supabase access. Backend ownership checks remain mandatory and
must not be replaced by RLS alone.

## Authority boundary

- Authorization defaults to deny and requires an explicit capability plus structured scope.
- Identity is injected from the verified Phase 1 context; request bodies cannot choose an owner,
  grant source, permission result, or authoritative risk.
- AAL2 account control is the bootstrap boundary for a user to grant their own permissions. It
  creates neither an administrator nor a universal permission.
- Risk classification uses only deterministic server-owned capability properties.
- Human confirmations are action-bound, expire, and are consumed when the policy requires a
  per-action approval.
- Financial execution is always denied in Phase 2. Permission and `auto_execute` cannot override
  this safeguard.
- Authorization and account-control mutations require audit evidence in the same transaction;
  an audit persistence failure rolls back and fails closed.
- Audit APIs are read-only and owner-scoped. Metadata is bounded and secret-redacted.

## Task Engine boundary

- Task ownership is derived only from verified identity; clients cannot choose owner or state.
- Task creation reuses Phase 2 authorization and preserves capability/action and financial guards.
- Terminal states cannot revive, stale versions cannot overwrite state, and claims are atomic.
- Authenticated clients cannot directly mutate Tasks, attempts, or append-oriented TaskEvents.
- Task metadata is bounded and processed by the shared secret redactor.
- PostgreSQL RLS runtime and simultaneous concurrency certification remain staging requirements.

## Memory boundary

- Memory ownership always comes from verified `IdentityContext`; public payloads cannot set owner,
  state, confidence, internal provenance, fingerprint, revisions, or embedding state.
- Memory operations require the server-owned Phase 2 capability/action vocabulary and fail closed.
  A future LLM may propose memory but has no persistence, ownership, or deletion authority.
- Content and metadata are bounded. Metadata uses centralized nesting limits and secret redaction;
  raw memory content is never written to structured logs or security audit metadata.
- Updates use optimistic versions and preserve pre-update revisions. Historical decisions cannot
  be overwritten.
- Archive preserves history but excludes records from normal retrieval. Privacy deletion is
  owner-scoped and irreversible through normal APIs; it scrubs current and revision content while
  retaining a minimal governance tombstone and content-free events.
- Expired records are excluded without requiring a cleanup worker. Discardable records are excluded
  from ordinary retrieval and all context packs unless explicitly queried.
- Authenticated Supabase roles receive owner-scoped SELECT only; direct memory mutation is denied.
  Runtime RLS and simultaneous PostgreSQL race certification require staging.

## AI Router boundary

- Providers/models, capability declarations, health, quality floors, sensitivity approvals, and
  budgets are server-owned. No public model/provider/safety override exists.
- The default catalog is disabled. `SENSITIVE` and `CRITICAL` context is never routed without
  explicit approval; uncertainty fails closed.
- Raw prompts, model outputs, Memory content, credentials, and tokens are excluded from routing
  evidence, usage telemetry, observer events, audit metadata, and default logs.
- Model output cannot bypass permissions, risk, confirmation, the financial guard, Task authority,
  Memory policy, or tool execution controls.
- AI routing/usage tables are owner-readable and backend-mutable only. Runtime RLS and real provider
  privacy/configuration certification require staging.

## Orchestrator boundary

- The Orchestrator coordinates existing authority services; it cannot grant permissions, lower
  risk, satisfy confirmations, select a model/provider, mutate Memory directly, or bypass Task
  transitions.
- Model text and structured JSON are untrusted proposals. Canonical capability/action validation
  and TaskService authority evaluation occur before any future-execution handoff.
- Plan fingerprints bind material arguments before authorization/confirmation. There is no public
  plan mutation, force-state, force-model, skip-confirmation, or envelope creation API.
- `SAFE_MODE` and `MAINTENANCE` can only restrict behavior. No feature flag or model output can
  override them, sensitivity policy, or the financial hard deny.
- Raw input, prompts, Memory content, and provider output are absent from workflow persistence,
  audit evidence, usage telemetry, and observability events.
- Phase 6 creates no Executor and performs no external side effect. Its internal immutable envelope
  must be independently revalidated by a future Executor.

## Text Assistant boundary

- Conversation ownership is derived from verified Identity; unknown or foreign identifiers return
  a non-leaking not-found response.
- Context contains only bounded complete recent messages and bounded `MemoryService` results.
- Current text and all context contribute to the highest effective sensitivity. Credential-shaped
  text is conservatively raised, and `CRITICAL` context requires approved local routing or denial.
- System instructions are centralized, server-owned, and cannot be overridden by user or provider
  content. Provider output remains untrusted data.
- Explicit Memory commands use the existing permission/risk/confirmation path. Inferred Memory is
  never persisted automatically.
- Action-shaped requests use the Orchestrator; Text Assistant cannot modify Task state or fabricate
  execution evidence. Financial execution remains impossible and no Executor exists.
- Message idempotency and optimistic conversation versions prevent duplicate or stale mutations.

## Realtime Voice boundary

- Voice is an interface, not authority. Only final validated transcripts enter the certified Text
  Assistant; partials cannot persist Memory, create action workflows, or confirm anything.
- Realtime microphone permission is just-in-time and capture exists only inside one explicit
  active `VoiceSessionController`. Phase 10 Wake capture is a separate local-only pre-activation
  pipeline and cannot access the realtime provider.
- Unknown audio is routed as CRITICAL/local-only by AI Router. No client provider/model override,
  external sensitivity fallback, or live provider is enabled by default.
- Session evidence is short-lived, hashed at rest, scoped to user/device/auth session/conversation,
  revalidated for revocation, and carried in a WSS header. Android receives no provider secret.
- Audio/network/playback/reconnect buffers and attempts are bounded. Barge-in invalidates old
  playback; stable turn identity prevents duplicate Conversation messages and workflows.
- Raw PCM, transcripts, Memory, prompts, responses, credentials, and authorization headers are
  absent from logs, Audit metadata, traces, crash metadata, and usage telemetry.
- Voice shares Orchestrator, Permission, Risk, Confirmation, Task, Safe Mode, and Financial Guard.
  It implements no Executor, side effect, or financial action.

## Wake Word boundary

- Wake is opt-in, device-specific, disabled by default, local-first, and never authenticates,
  authorizes, confirms, changes policy, writes Memory, calls a provider/Executor, or executes.
- The microphone service is user-initiated, visible, non-exported, correctly typed, and
  `START_NOT_STICKY`; reboot/process recreation cannot silently restart it.
- Pre-wake PCM is fixed-frame, transient, untranscribed, unpersisted, unlogged, and never sent over
  the network. Detection events contain metadata only.
- Auth, registered Device, lock screen, power/thermal state, event age/profile/device binding,
  debounce, and durable replay identity are checked before the sole Phase 9 handoff.
- No production detector falls back to cloud STT. An approved offline model and hardware
  validation remain explicit requirements.

## Reporting a vulnerability

Do not disclose a suspected vulnerability publicly. Until an approved private reporting channel
exists, notify the repository owner privately through the collaboration channel already used for
the project. Include reproduction steps and impact, but do not include real credentials.
