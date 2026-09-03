# Personal Assistant

A security-conscious, multi-device personal assistant foundation. The approved direction is a
modular monolith with a Python/FastAPI backend, future Supabase/PostgreSQL persistence, Railway
deployment, and GitHub as the canonical source with GitHub Actions CI.

**Current phase: PHASE 12 — WEB CLIENT**

**Current version: 0.13.0 — Web Research**

## Current state

Phase 2 adds a default-deny authorization boundary on top of Phase 1 identity: structured
capabilities and scopes, temporary and device-scoped permissions, deterministic risk
classification, human confirmation requests, an absolute financial-execution guard, and
append-oriented audit evidence. It produces `ALLOW`, `DENY`, or `REQUIRE_CONFIRMATION` decisions.
It does not execute actions.

Each capability owns its server-defined action vocabulary. Permission scopes can narrow that
authority but cannot invent operations; invalid pairs are rejected at grant time and denied again
at authorization time before risk classification.

Phase 3 adds persisted Tasks, a deterministic state machine, user-scoped idempotency, optimistic
version checks, cancellation and expiration, TaskAttempt and append-oriented TaskEvent history,
and a controlled future-worker claim boundary. It executes no Task and adds no worker or queue.

Phase 4 adds owner-scoped classified memory, explicit provenance, bounded content/metadata,
deterministic exact deduplication, optimistic updates, reconstructable revisions, archive,
privacy deletion with content scrubbing, lazy expiration, deterministic bounded retrieval, and a
future-Orchestrator context-pack boundary. Memory operations reuse Phase 2 permissions, risk,
confirmation, and audit; no model can persist memory directly.

Phase 5 adds an internal provider-independent AI Router: a disabled-by-default server-owned model
catalog, deterministic smallest-sufficient quality routing, sensitivity approval, context/output
limits, equivalent-quality fallback, bounded retries, provider health, cost estimates/budgets,
privacy-safe decisions/usage, and OpenTelemetry-ready events. It exposes no public prompt proxy,
enables no live provider, and gives model output no tool or action authority.

Phase 6 adds a typed, durable Orchestrator that coordinates verified identity, bounded Memory
context, AI Router decisions, schema-validated proposals, Task creation, and the certified
Permissions/Risk/Confirmation/Financial Guard chain. It adds deterministic safe modes,
idempotency, immutable plan fingerprints, optimistic workflow transitions, audit evidence, and an
internal future-executor envelope. The envelope is evidence for later revalidation, not authority.

Phase 7 adds durable owner-scoped conversations, bounded recent-history context, explicit Memory
commands, conservative text sensitivity classification, AI Router-only provider invocation, and
truthful action coordination through the Orchestrator. Conversation history never becomes Memory
automatically. Local certification uses deterministic fake providers; the shipped provider catalog
remains disabled until approved runtime configuration exists.

Phase 8 adds the first Android client under `mobile/`: KMP contracts and typed API transport,
Supabase-compatible session handling protected by Android Keystore, app-scoped installation
identity, Device registration, Compose conversation UI, validated connectivity state, encrypted
Room cache, and bounded WorkManager delivery using stable idempotency identities. It implements no
Executor, external side effect, or financial operation. The backend remains the authority for
identity, policy, conversation, memory, routing, orchestration, confirmation, tasks, Safe Mode,
and financial denial.

Phase 9 adds one scoped realtime voice interface over the same Conversation and Text Assistant.
Android owns JIT microphone capture, bounded PCM playback, audio focus, lifecycle cleanup, and a
single `VoiceSessionController`. The backend owns expiring session evidence, REALTIME routing,
partial/final transcript separation, turn idempotency, and the final bridge through Memory and
Orchestrator. Unknown microphone ingress is conservatively CRITICAL and local-only until a final
transcript exists. No provider credential reaches Android, no live provider is enabled by default,
and Wake Word remains out of scope.

Phase 10 adds an opt-in, local-first Wake Word activation boundary in front of the same Phase 9
`VoiceSessionController`. A user-initiated, visible microphone foreground service hosts a bounded,
provider-independent local detector; metadata-only detections pass through device/auth/lock/power,
debounce, stale-event, and durable replay checks before Voice starts. No pre-wake audio leaves the
device or persists, process death/reboot cannot restart capture, and Wake gains no permission,
confirmation, routing, Memory, Safe Mode, Task, financial, or execution authority. The approved
production model remains `REQUIRES MODEL TRAINING`; the release fails honestly rather than using
cloud transcription or an unreviewed SDK.

Phase 11 evolves the single Phase 8 delivery route into a typed, owner/device-bound offline
transport system. Encrypted pending intent survives restart with stable operation and idempotency
identity; atomic claims, bounded classified retry, event-driven backend reachability, and
server-idempotent reconciliation converge after ambiguous failures. Local pending, stale cache,
server acknowledgement, rejection, authentication wait, and cancellation races remain visibly
distinct. The server re-evaluates every new submission through the certified Text Assistant,
Memory, Orchestrator, Permissions, Risk, Confirmation, Safe Mode, and financial-deny authorities.
No offline LLM, raw-audio queue, cloud wake fallback, general Executor, or local authority was added.

Phase 12 adds a strict TypeScript/React web interface over the same certified backend. Supabase
Auth remains the only identity provider; browser tokens and server state remain memory-only, and a
minimal same-origin Node process serves the production bundle and proxies only certified API
routes. The client supports conversations, truthful Text Assistant outcomes, explicit Memory
controls, read-only Assistant permissions, server Confirmation controls, responsive accessible
layouts, and honest offline degradation. It adds no browser Voice/Wake path, client authority,
durable offline queue, general Executor, financial execution, or Web Research.

Task execution, real model calls, embeddings generation, semantic ranking, production wake model,
automations, financial actions, external integrations, functional desktop clients, and Web Research
are not implemented. No LLM, capability, automation, or future agent can grant itself authority,
bypass memory policy, or execute a tool. Permission administration and confirmation require an
authenticated AAL2 account-control flow.

## Local web client

Requirements: Node.js 24 and npm 11.

```bash
cd apps/web
npm ci
cp .env.local.example .env.local
npm run dev
```

Set only the local backend proxy and public Supabase URL/key in `.env.local`. Production uses the
server-only values documented in `apps/web/.env.production.example`; no backend destination is
accepted from browser input. Production deployment is intentionally not performed by Phase 12.

## Local backend

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
uv sync --all-extras
uv run python -m backend.app
```

The backend listens on `PORT` when set, otherwise `8000`. Health endpoints are available at
`/health/live` and `/health/ready`. They remain available without Supabase credentials.

Authenticated endpoints require:

- `DATABASE_URL` using PostgreSQL/asyncpg in deployed environments;
- `SUPABASE_URL`, or explicit `SUPABASE_JWT_ISSUER` and `SUPABASE_JWKS_URL`;
- `SUPABASE_JWT_AUDIENCE`, normally `authenticated`.

`SUPABASE_SERVICE_ROLE_KEY` is not used by Phase 2. No authentication bypass environment
variable exists.

## Migrations

```bash
uv run alembic upgrade head
uv run python -m scripts.validate_migrations
```

The validation script executes clean upgrade, downgrade, and re-upgrade against an isolated
database. Production schema changes must always use Alembic.

## Identity API

- `GET /api/v1/me`
- `POST /api/v1/devices/register`
- `GET /api/v1/devices`
- `POST /api/v1/devices/{device_id}/revoke`

All endpoints require a verified Supabase bearer token. After registration, clients may send the
returned device UUID in `X-Device-ID`; the backend accepts it only when it belongs to the
authenticated user and is not revoked.

## Authority API

- `POST /api/v1/authorization/evaluate`
- `GET /api/v1/permissions`
- `GET /api/v1/permissions/{permission_id}`
- `POST /api/v1/permissions/grant` (AAL2, own account only)
- `POST /api/v1/permissions/{permission_id}/revoke`
- `POST /api/v1/confirmations/{confirmation_id}/approve` (AAL2)
- `POST /api/v1/confirmations/{confirmation_id}/reject` (AAL2)
- `GET /api/v1/audit?limit=50&offset=0`

## Task API

- `POST /api/v1/tasks`
- `GET /api/v1/tasks`
- `GET /api/v1/tasks/{task_id}`
- `POST /api/v1/tasks/{task_id}/cancel`

There is no public arbitrary-state, claim, completion, failure, retry, or Executor endpoint.

## Memory API

- `POST /api/v1/memories`
- `GET /api/v1/memories`
- `GET /api/v1/memories/{memory_id}`
- `GET /api/v1/memories/{memory_id}/revisions`
- `PATCH /api/v1/memories/{memory_id}`
- `POST /api/v1/memories/{memory_id}/archive`
- `DELETE /api/v1/memories/{memory_id}?expected_version=N`

Public creation records only explicit-user provenance. Internal Task, System, Device, and Import
proposals pass through the same Memory Service policy; future AI proposals cannot persist in Phase
4. Normal retrieval excludes archived, expired, deleted, and—unless explicitly requested—
discardable records. Deleted content has no restore route.

The evaluation endpoint accepts a proposal, never caller-supplied authority. Fields such as
`user_id`, `permission_granted`, and top-level risk declarations are rejected. Financial
execution remains denied even if a permission record or `auto_execute` value is misconfigured.

## AI Router boundary

The AI Router is internal only. There is no `/api/v1/ai` completion endpoint and no public model,
provider, sensitivity, quality, health, or budget override. The bundled catalog is intentionally
disabled until a later approved provider configuration exists. See
`docs/architecture/ai-router.md`, `docs/security/ai-router.md`, and
`docs/operations/ai-cost-usage.md`.

## Orchestrator API and boundary

- `POST /api/v1/orchestrations`
- `GET /api/v1/orchestrations`
- `GET /api/v1/orchestrations/{workflow_id}`
- `POST /api/v1/orchestrations/{workflow_id}/cancel`
- `POST /api/v1/orchestrations/{workflow_id}/resume`

The API accepts no owner, provider, model, risk, permission, confirmation-satisfied, sensitivity,
safe-mode, state, or execution authority fields. It exposes no plan mutation, arbitrary state,
tool execution, or authorized-envelope endpoint. The default AI catalog remains disabled; local
tests use only dependency-composed deterministic fake providers.

## Text Assistant API

- `POST /api/v1/conversations`
- `GET /api/v1/conversations`
- `GET /api/v1/conversations/{conversation_id}`
- `POST /api/v1/conversations/{conversation_id}/messages`
- `GET /api/v1/conversations/{conversation_id}/messages`

Message submission requires an idempotency key and expected conversation version. It exposes no
raw completion, model/provider override, tool, force-memory, force-state, system-prompt, or
execution endpoint. A future-action response never claims completion because Phase 7 has no
Executor.

## Realtime Voice API and boundary

- `POST /api/v1/voice/sessions`
- `POST /api/v1/voice/sessions/{session_id}/credential`
- `POST /api/v1/voice/sessions/{session_id}/end`
- `WSS /api/v1/voice/sessions/{session_id}/stream`

The stream uses a short-lived, session/device/user-bound header credential and never exposes a
provider key to Android. Partial transcripts are UI-only; exactly one final turn crosses into Text
Assistant. Unknown microphone audio is CRITICAL/local-only until classified, so the default empty
provider registry fails honestly. See `docs/architecture/realtime-voice.md`,
`docs/security/realtime-voice.md`, and `docs/decisions/ADR-0010-realtime-voice-boundary.md`.

## Wake Word boundary

Wake Word is disabled by default and can be enabled only from visible UI after a privacy notice and
JIT microphone permission. Manual and wake activation converge before the existing Phase 9
VoiceSession. Screen-off, process death, reboot, permission loss, power saver, and thermal limits
fail closed; no background workaround or default-assistant role is used. See
`docs/architecture/wake-word.md`, `docs/security/wake-word.md`, and
`docs/decisions/ADR-0011-wake-word-activation.md`.

## Quality checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy backend shared scripts tests
uv run python -m scripts.validate_migrations
uv run pytest
python -m compileall -q backend shared scripts tests
```

## Repository layout

- `apps/`: reserved device clients.
- `backend/`: FastAPI modular monolith.
- `shared/`: future cross-platform contracts.
- `infrastructure/`: provider-specific documentation and placeholders.
- `tests/`: unit, integration, security, regression, and scenario suites.
- `docs/`: architecture, security, operations, decisions, and certification records.

See `docs/architecture/text-assistant.md`, `docs/security/text-assistant.md`, and
`docs/decisions/ADR-0008-text-assistant.md` for the Phase 7 boundary.

## Android client

Requirements for a local Android build are JDK 17 and Android SDK 35.

```bash
cd mobile
./gradlew :shared:desktopTest :androidApp:testLocalDebugUnitTest :androidApp:lintLocalDebug
./gradlew :androidApp:assembleLocalDebug :androidApp:assembleProductionRelease
```

`localDebug` alone permits cleartext to the emulator loopback address. Staging and production
URLs are build-controlled Gradle properties and must use HTTPS. Supabase anon keys are runtime
client identifiers, not service-role credentials; no default credential is shipped. See
`docs/architecture/android-agent.md` and `docs/security/android-agent.md`.
