# Offline System architecture

Phase 11 treats offline operation as transport state, never authorization. The Android client may
persist encrypted pending intent, cached server representations, operation identity, and sync
metadata. Identity, permission, risk, confirmation, sensitivity, routing, orchestration, Memory,
Safe Mode, financial denial, and completed server state remain server-owned.

## Source of truth

Only a persisted backend response is confirmed server state. Room holds local pending state or a
bounded cached representation and never overrides current server policy.

## Canonical path

`Compose UI → ConversationRepository → Room pending operation → DeliveryScheduler →
MessageDeliveryWorker → ConversationRepository.deliver → Text Assistant API`

There is one network delivery caller: `MessageDeliveryWorker`. Manual retry, restart recovery, and
reconnect coordination only schedule the existing `operationId` through unique work
`message:<operationId>` with `KEEP`. They never call the backend themselves.

## Connectivity

The local monitor emits `OFFLINE`, `DEGRADED`, `RECOVERING`, or `UNKNOWN` from event-driven Android
network callbacks. A validated interface enters `RECOVERING`, not `ONLINE`. The coordinator performs
one backend liveness probe for that transition. A successful backend response establishes `ONLINE`;
transport timeout/unavailability establishes `DEGRADED`. Authentication and policy errors still
prove the backend is reachable and therefore do not masquerade as offline state. There are no
polling loops, wake locks, or connectivity-triggered AI calls.

## Durable operation

Each text-message intent stores one stable `operationId` and derived `android:<operationId>`
idempotency key. The encrypted payload is bound by a SHA-256 fingerprint to its operation type,
conversation, idempotency key, expected version, and content. Rows also contain payload version,
authoritative user/device binding, timestamps, bounded attempt metadata, acknowledgement time, and
safe failure category/code. No access token, refresh token, credential, raw audio, provider secret,
or server authority snapshot is stored in Room.

The Room 1→2 migration preserves terminal historical outcomes but rejects non-terminal Phase 8
rows whose user/device ownership cannot be proven. It never guesses ownership. Fresh and migrated
databases use the same schema and production has no destructive migration fallback.

## State machine

| State | Meaning | Automatic replay |
| --- | --- | --- |
| `PENDING` | Saved locally; no server claim | Yes |
| `WAITING_FOR_NETWORK` | Awaiting verified reachability | Yes |
| `SYNCING` | Atomically claimed by one worker | No concurrent claim |
| `ACKNOWLEDGED` | Server response persisted locally | Terminal |
| `RETRYABLE_FAILURE` | Classified transient failure | Yes, bounded |
| `AUTH_REQUIRED` | Current credentials cannot establish authority | No |
| `REJECTED` | Server policy/conflict/revocation rejection | Terminal |
| `CANCEL_REQUESTED` | Send raced with cancellation; server result unknown | No blind replay |
| `CANCELLED` | Cancelled before a worker claimed it | Terminal |
| `TERMINAL_FAILURE` | Validation, integrity, or retry-exhaustion failure | Terminal |

Illegal transitions fail closed. A compare-and-set Room update claims work only from eligible state,
for the current owner/device, and below the attempt bound. Duplicate workers and callbacks therefore
cannot produce concurrent submissions or overwrite terminal truth. A late authoritative ACK may
replace `CANCEL_REQUESTED`; local cancellation can never replace an ACK.

## Retry and reconciliation

Only network failure, timeout, and temporary server unavailability explicitly marked retryable are
retried. Authentication waits for user action. Authorization, permission, confirmation, Safe Mode,
device revocation, idempotency conflict, validation, and permanent server errors do not retry.
Attempts stop at five. WorkManager supplies constrained exponential backoff; durable metadata records
a capped, stable per-operation 80–120% jitter target to prevent synchronized reconnect storms.

If the server commits but the response is lost, process recovery changes interrupted `SYNCING` to
`RETRYABLE_FAILURE`. The worker resubmits the identical request with the identical idempotency key
and fingerprint. The certified Text Assistant checks idempotency before conversation version and
returns the stored authoritative response. A changed payload under that key is a permanent conflict.
No new backend endpoint or migration is required.

## Restart, account, device, and multi-device behavior

Room and WorkManager survive process death. Startup recovery resets only interrupted claims and
unique scheduling converges with any already-persisted worker. Auth-required rows are not hammered.
Logout cancels tagged work before clearing Room and encrypted session/binding material. Re-auth for
the same owner can resume auth-waiting intent; a changed user or device clears old cached data before
the new binding is stored. Device revocation clears work, cache, and credentials. Every replay still
uses the server-bound user/device headers, so one device cannot replay another device's row.

Conversation versions make concurrent multi-device changes explicit. Server state wins: a stale
version becomes a non-retryable conflict. Security-sensitive conflicts never use last-write-wins.

## Cache and interface behavior

Conversation messages are encrypted and bounded to 200 per conversation. Active pending operations
are capped at 100; terminal metadata expires after seven days. CRITICAL data is not eligible for
stale display. Connectivity and row state label cached, pending, syncing, accepted, rejected,
auth-required, cancelled, and unknown-server-result conditions separately.

Offline Text Assistant stores intent but fabricates no answer. Voice reports unavailable unless the
backend connection is verified. Wake detection may remain local under its Phase 10 policy, but its
gateway refuses downstream Voice activation offline. No PCM/audio is persisted, no cloud Wake/STT
fallback exists, and offline conversation never becomes Memory without the normal server path.
