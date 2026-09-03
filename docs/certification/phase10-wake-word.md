# Phase 10 — Wake Word validation record

Version: 0.10.1

Baseline: `personal-assistant-0.9.0-realtime-voice.zip`

Baseline SHA-256:
`ca6ffc3b66844bacf1bbe3f6e9ece9b39109866bdebb9fff17e8e0b1b541c9fe`

## Implemented boundary

- KMP wake contracts, explicit state machine, authority invariants, metrics, event validation,
  debounce, durable activation identity, and one canonical Phase 9 gateway.
- Android opt-in/JIT UI, device-local preference, non-exported visible microphone foreground
  service, keyguard/auth/device/power/thermal policy, fixed-frame AudioRecord engine, and local
  detector abstraction.
- No cloud wake detection, ambient transcript, pre-roll, boot receiver, hidden microphone,
  VoiceInteractionService/default-assistant role, new backend API/table/migration, Executor,
  external side effect, or financial execution.
- Production detector fails closed until an approved offline model is integrated. The fake engine
  is test-source-only and follows the same policy/gateway contracts.

## Certification correction

- Replaced the non-public PackageManager permission-change listener with the public,
  event-driven `AppOpsManager.OnOpChangedListener` for `OPSTR_RECORD_AUDIO`.
- The listener remains scoped to this package, rechecks the actual runtime permission, suspends
  capture on revocation, and is unregistered during service teardown.
- Activation replay identity is committed on the IO dispatcher and persistence failure stops the
  handoff before VoiceSession begins; this preserves process-death correctness without main-thread
  disk I/O.
- Local cleartext HTTP/WebSocket support is controlled by a flavor-owned BuildConfig boolean;
  staging and production compile it as false and retain system-CA-only release networking.

## Local validation

- Backend full regression: 772 passed.
- Backend security suite: 276 passed.
- Phase 9 Python regression: 60 passed; KMP/Android voice tests: 25 passed.
- Phase 10 focused Python integration/security block: 147 passed.
- Phase 10 Python/static contract tests: 53 collected and passed.
- Phase 10 KMP tests: 29 passed; total KMP suite: 73 passed.
- Phase 10 Android unit tests: 15 passed; total Android unit suite: 38 passed.
- Clean `localDebug` build and lint: PASS; lint reports zero issues.
- Clean minified `productionRelease` build and lint: PASS; lint reports zero issues.
- Final merged manifest review: PASS for target SDK 35, explicit `RECORD_AUDIO`,
  `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MICROPHONE`, non-exported microphone service, and
  `foregroundServiceType="microphone"`.
- Release network security: PASS; cleartext is disabled, only system trust anchors are configured,
  and the release DEX contains no local emulator HTTP/WebSocket endpoint.
- Release APK/source secret and production-test-implementation scan: PASS.
- Gradle production runtime and KMP test dependency resolution: PASS offline against the resolved
  lock/catalog, with no new dependencies.
- Ruff format/lint: PASS.
- mypy: PASS.
- Python compile/startup/health: PASS.
- Migration upgrade/downgrade/re-upgrade/drift: PASS.
- Historical migrations 0001–0009: byte-identical.
- Python dependency audit: no known vulnerabilities; first-party package is not a PyPI subject.
- Gradle dependency catalogs/lockfiles: byte-identical to Phase 9; dependencies added: none.
- Manifest/network/XML/source secret static review: PASS.
- Release output is the expected unsigned production APK because no private signing key is stored
  in the project; signing/deployment is outside this source certification and no APK is packaged.

The merged manifest contains WorkManager's non-exported, disabled `RescheduleReceiver` and its
`BOOT_COMPLETED` filter. No application receiver or wake component handles boot, and no boot path
starts the microphone or wake foreground service.

## Hardware validation boundary

Real microphone, background transition, notification, screen lock, incoming call, Bluetooth,
wired headset, permission revocation, process death, power saver, thermal behavior, CPU/battery,
and false-positive/negative performance remain `REQUIRES ANDROID RUNTIME TEST`.

An approved local detector model and phrase training remain `REQUIRES MODEL TRAINING`. The current
release intentionally reports engine unavailable instead of pretending hands-free production
detection or falling back to cloud STT.

## External state

- External services modified: none.
- Production modified: none.
- Secrets added: none.
- Backend migration added: none.
- Phase 11 implemented: no.
