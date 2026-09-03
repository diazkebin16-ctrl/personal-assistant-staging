# Phase 9 Realtime Voice certification scope

Version: 0.9.0

Phase 9 implements a single scoped realtime voice path across KMP contracts, native Android audio,
secure WebSocket transport, backend session/turn persistence, AI Router, and the certified Text
Assistant. It covers explicit states, JIT microphone permission, bounded audio/network buffers,
partial/final separation, barge-in, cancellation, bounded reconnect, turn idempotency, truthful
outcomes, privacy-safe observability, and backend-only RLS.

Certification uses a deterministic local fake realtime provider. The production registry remains
empty, unknown audio is routed as CRITICAL/local-only, and no production credential or provider is
enabled. No Executor, external side effect, provider secret, Wake Word, always-listening service,
Phase 10 feature, external service mutation, or production modification is included.

Local evidence includes backend Phase 0–9 regression, focused security/integration tests, migration
upgrade/downgrade/re-upgrade/drift validation, static pgTAP/RLS review, KMP/JVM tests, Android unit
tests, lint, local debug assembly, production release assembly, manifest/network review, secret
scan, and dependency audit.

Final local results: 718/718 backend tests, including 239 security tests and 60 focused Phase 9
tests; 44/44 KMP/JVM tests; 23/23 Android unit tests; lint, clean local debug build, and clean
production release build passed. Historical migrations `0001`–`0008` match their certified hashes.
The dependency coordinate/version sets are exactly unchanged from the certified Phase 8 baseline
(40 Python, 272 Android lock entries, and 147 shared lock entries); Phase 9 only makes existing
OkHttp/serialization transitives direct compile dependencies. A fresh offline OSV refresh could not
load a local vulnerability database, so this evidence relies on the certified baseline audit plus
an exact zero-version-delta comparison rather than claiming a new networked OSV result.

The final clean multi-variant build also removed a reproducibility defect in inherited build
configuration: Room/KSP variants shared one schema export while Gradle parallelism was enabled,
which could leave duplicate generated DAO output. Project-level parallelism is now disabled and
the combined clean KMP/unit/lint/debug/release command passes without exclusions or suppressed
errors.

The following cannot be truthfully certified without external runtime:

- `REQUIRES ANDROID RUNTIME TEST`: microphone/speaker, focus, wired/Bluetooth routes, screen lock,
  actual barge-in latency, lifecycle/process death, Compose accessibility, and device APK behavior.
- `REQUIRES STAGING`: Supabase RLS, JWT/JWKS, revocation, PostgreSQL simultaneous races, and backend
  TLS/WSS deployment.
- `REQUIRES REAL PROVIDER TEST`: approved adapter compatibility, VAD/transcription, streaming
  synthesis, audio quality, latency, disconnects, and real cost.
