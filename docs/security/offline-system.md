# Offline System security

## Trust boundary

Room, WorkManager input, Android connectivity callbacks, UI controls, cached content, and retry
metadata are untrusted transport inputs. The backend remains the source of truth and re-runs the
certified Text Assistant, Orchestrator, Permissions, Risk, Confirmation, Safe Mode, sensitivity,
Memory provenance, and `FinancialExecutionGuard` paths for every new submission.

The offline client cannot mint confirmation, permission, server task/memory state, model/provider
selection, sensitivity, safe-mode state, an authorized action envelope, or execution authority.
There is still no Executor and no financial execution endpoint or queue type.

## Protections

- Pending content is AES-GCM encrypted by the Android Keystore-backed local cipher.
- A canonical SHA-256 fingerprint binds content to operation type, conversation, expected version,
  and stable idempotency identity. Cipher authentication or fingerprint mismatch fails terminally.
- Atomic owner/device/state/attempt compare-and-set claims reject duplicate workers and cross-boundary
  replay. Unknown state or payload version fails closed.
- The server's user-scoped idempotency fingerprint reconciles response loss and rejects mutated
  payload reuse. Local success is written only in the transaction that caches a server response.
- Retry classification is an allowlist. 401, 403, confirmation/permission/Safe Mode rejection,
  device revocation, 409, 422, permanent 4xx, and local integrity failures never loop.
- Startup and reconnect scheduling are serialized, event-driven, bounded, and use WorkManager
  unique work with network constraint and exponential backoff.
- Logout/account switch cancels work before data clearance. Rows never execute under a different
  owner or registered device. Revocation clears cached sensitive material and credentials.
- Telemetry is metadata-only: state, attempt count, connectivity, latency class, and failure category.
  Content, transcript, Memory, token, header, raw audio, and CRITICAL payload are excluded.

## Cancellation race

Before atomic claim, cancellation marks the row `CANCELLED` and cancels unique work. During a send,
the system records `CANCEL_REQUESTED`: it does not claim the server cancelled and does not blindly
replay a possibly committed request. A late server ACK becomes `ACKNOWLEDGED`, because server truth
outranks local intent. The UI labels the ambiguous state as requiring attention.

## Attack review

The Phase 11 suite attacks queue/idempotency mutation, encrypted-payload tampering, unknown state and
payload version, cross-user/device replay, duplicate worker/callback, reconnect amplification,
process death around commit, stale conversation version, logout/login and account switch, expired
authentication/confirmation, revoked permission/device, Safe Mode, financial bypass, sensitivity
downgrade, raw-audio persistence, cloud Wake fallback, cached-authority escalation, and fabricated
offline answers. Permanent results are not made retryable to satisfy tests.

No new runtime dependency, Android permission, backend migration, external service, production
setting, provider, model, secret, or network-security exception is introduced by Phase 11. The
certification correction adds only the official Room Gradle plugin at the already-pinned Room
version so schema export is declared and reproducible; it does not enter an application runtime
classpath.
