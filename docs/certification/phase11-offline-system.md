# Phase 11 — Offline System certification

Status: **PASS — PHASE 11 COMPLETE**

Final version: **0.11.1**

Phase 12 started: **no**

## Artifact lineage and interrupted-run recovery

Certified Phase 10 baseline: `personal-assistant-0.10.1-wake-word-certified.zip`

Certified Phase 10 baseline SHA-256:
`cd65c9801e808ab31a890fc71cb935aec178b6b803320b8836d843095522b63e`

Certification input: `personal-assistant-0.11.0-offline-system.zip`

Certification input SHA-256:
`22996cccfd121567428ed1688c04c131ed732b4c0fb97af125ca6d78d7e7d740`

The continuation workspace was inspected before execution. Its source tree was absent after the
manual interruption, so integrity could not be established from that tree. The exact Phase 11
candidate named above was therefore recovered, its SHA-256 was verified, all 355 ZIP entries passed
integrity testing, and every entry was checked for safe extraction. Phase 11 was not reconstructed
from the Phase 10 baseline.

Android Build Tools 34.0.0 was found partially installed. Only the incomplete external toolchain
installation was quarantined and replaced. The final installation reports revision 34.0.0, has no
installer marker or temporary payload, and its `aapt2`, `apksigner`, `d8`, and `zipalign` commands
execute. No source was changed to compensate for that runner failure.

Previously fetched dependency data was retained. At final validation the external Gradle module
cache contained 885 files, the Maven mirror cache contained 1,856 files (496,292,108 bytes), and the
Python environment contained 40 locked distributions. All runner init scripts, SDKs, JDKs, mirror
data, project caches, and temporary properties remained outside the repository.

## Scope

Phase 11 evolves the certified Android delivery path into a typed, owner/device-bound offline state
machine with bounded retry, process-death recovery, server-idempotent response-loss reconciliation,
Room schema 2 and migration 1→2, and truthful cached/pending/sync/ACK/rejected/auth-required UI.
It preserves one WorkManager delivery authority, the existing backend authorization chain, the
Phase 9 Voice gateway, the Phase 10 Wake boundary, Safe Mode, confirmation, and the financial hard
deny. It adds no backend migration, application runtime dependency, Android permission, external
service, production setting, secret, Executor, parallel delivery path, offline LLM, raw-audio
persistence, or cloud Wake provider.

## Certification corrections and root causes

Source/configuration corrections were required, so the coherent project version is 0.11.1.

1. Two expression-bodied KMP tests returned the exception captured by `assertFailsWith`, not
   `Unit`; JUnit rejected those test signatures during initialization. They now use block bodies and
   retain the same exception assertions.
2. The Gradle wrapper declared a checksum that did not match the official Gradle 8.9 archive. The
   property now contains the independently verified archive SHA-256
   `d725d707bfabd4dfdc958c624003b3c80accc03f7037b5122c4b1d0ef15cecab`.
3. Room schema export used an undeclared raw KSP argument, schema 2 was missing from source, and
   concurrent Android variant processors could contend for the same output. The Android module now
   uses the official Room 2.6.1 Gradle plugin, declares the authoritative schema directory, keeps
   KSP variant tasks ordered, and includes the generated schema 2 history.
4. KSP 1.0.29 could leave its byte-identical transient `byRounds` Java shadow under generated
   sources, causing `javac` duplicate-class failures. Java compilation now excludes only that KSP
   internal shadow directory; the canonical generated sources remain compiled.
5. Three Phase 11 Python test files did not satisfy the repository's enforced Ruff format policy.
   They were formatted without changing assertions or coverage.

Focused regressions were added for schema 2 and the Room/KSP build contract. No patch, bypass, test
weakening, duplicated authority, or duplicated delivery path was introduced.

## Files created or modified

Created:

- `mobile/androidApp/schemas/com.personalassistant.android.data.local.AssistantDatabase/2.json`

Modified for certification fixes, coherent versioning, tests, or documentation:

- `.env.example`
- `CHANGELOG.md`
- `README.md`
- `backend/app/core/config.py`
- `docs/certification/phase11-offline-system.md`
- `docs/security/offline-system.md`
- `mobile/androidApp/build.gradle.kts`
- `mobile/build.gradle.kts`
- `mobile/gradle/libs.versions.toml`
- `mobile/gradle/wrapper/gradle-wrapper.properties`
- `mobile/shared/src/commonTest/kotlin/com/personalassistant/shared/OfflineSemanticsTest.kt`
- `pyproject.toml`
- `tests/integration/test_android_agent_contract.py`
- `tests/integration/test_android_room_migration.py`
- `tests/integration/test_offline_system_contract.py`
- `tests/integration/test_wake_word_contract.py`
- `tests/security/test_offline_system_security.py`
- `tests/unit/test_application.py`
- `uv.lock`

Deleted source files: none.

## Mandatory gate results

| Gate | Result | Verifiable evidence |
| --- | --- | --- |
| Python lock/install | PASS | Frozen resolution; 40 installed distributions; `pip check` clean |
| Ruff format | PASS | 256 files already formatted |
| Ruff lint | PASS | No findings |
| mypy strict | PASS | 187 source files; no findings |
| Python compile | PASS | `compileall` completed |
| Backend full regression | PASS | 851 passed, 0 failed |
| Backend security | PASS | 313 passed, 0 failed |
| Phase 11 focused | PASS | 79 passed, 0 failed |
| Phase 8 regression | PASS | 88 passed, 0 failed |
| Phase 9 regression | PASS | 58 passed, 0 failed |
| Phase 10 regression | PASS | 53 passed, 0 failed |
| KMP/JVM | PASS | 140 passed, 0 failed/errors/skipped |
| Android unit | PASS | 275 passed across 5 variants; 0 failed/errors/skipped |
| Android lint | PASS | Clean run; 0 issues; warnings are errors |
| Clean local debug | PASS | 58 tasks; build successful |
| Clean production release | PASS | 86 tasks; minification/resource shrinking/build successful |
| Room schema 2 | PASS | Version 2; identity `b864c2c06ef4c913d872f675c6bafa58` |
| Room migration 1→2 | PASS | 5 focused schema/migration tests passed |
| Merged production manifest | PASS | Compiled APK and merged-source assertions passed |
| Release network security | PASS | Cleartext false; system trust only; no user anchors |
| APK endpoint/secret scan | PASS | No deliverable local endpoint or recognized secret signature |
| Source/archive secret scan | PASS | No real env, private key, credential, keystore, database, log, APK, or AAB packaged |
| Gradle dependency resolution | PASS | Production runtime and desktop test reports clean; lockfiles unchanged |
| Dependency security audit | PASS | `pip-audit`: 0 known; OSV: 0 known across 277 Maven coordinates |
| Backend migration validation | PASS | Upgrade, downgrade/re-upgrade, and drift validation passed |
| Deterministic packaging | PASS | Independent preflight archives were byte-identical |

The final Android unit gate was rerun after the last KSP configuration correction. The KMP gate was
also rerun after all source/configuration changes. No interrupted process is counted as PASS.

## Offline and security invariants

- Offline state-machine, retry classification, stable jitter, queue bounds, reconnect-storm
  control, account/device binding, and fail-closed unknown-state/version behavior: PASS.
- Process-death claim recovery, durable activation/operation identity, duplicate callback/worker
  handling, response-loss reconciliation, cancellation/late-ACK truth, and server ACK authority:
  PASS.
- Expired authentication/confirmation, permission/device revocation, Safe Mode, financial hard
  deny, sensitivity downgrade, raw-audio persistence, cloud Wake fallback, cached-authority
  escalation, and fabricated offline-answer attacks: PASS.
- Security findings after tests, static checks, dependency audits, manifest/network review, and
  source/APK scans: critical 0, high 0, medium 0, low 0.

The production APK used for binary inspection was the expected unsigned artifact because no signing
key is stored in the project. It was aligned, 1,580,598 bytes, and had SHA-256
`c06e914c724b68e3aa0654f320ca45e9702b0a03f8b3df221b7df99b54139f3b`. The generic
`http://localhost` string in minified DEX was traced through the R8 mapping to
`io.ktor.http.URLBuilder`; production `BuildConfig` contains `https://production.invalid/`, and the
release DEX contains no emulator/loopback HTTP endpoint or local WebSocket endpoint.

Room schema 1 remains byte-identical with SHA-256
`3e2a72a376cccc05653250ce33cd4f09b555468cc1ce6f73fc739f046a19d159`. Schema 2 has SHA-256
`2a31381d3fa64fec83fd59b928a61ab00d7f68e9b5304e849a438d528160a828`. Backend migrations
`0001`–`0009` are byte-identical to the certification input, migration validation reports no drift,
and backend migration `0010` does not exist.

## Known external validation boundaries

- **REQUIRES ANDROID RUNTIME TEST:** physical/emulated process death, actual WorkManager scheduling
  and OS backoff, encrypted Room migration on-device, real connectivity transitions, UI
  accessibility, microphone/speaker/audio routes, lifecycle, power/thermal behavior, and packaged
  APK device behavior.
- **REQUIRES STAGING:** live Supabase RLS/JWT/JWKS/revocation, PostgreSQL concurrency, TLS/WSS,
  multi-device conflict, server response loss, and deployed permission/confirmation/Safe Mode
  changes.
- **REQUIRES REAL PROVIDER TEST:** approved realtime provider interoperability, audio quality,
  latency, disconnect behavior, and cost.
- **REQUIRES MODEL TRAINING:** the inherited Phase 10 local Wake detector model and phrase-quality
  validation. Production detection continues to fail closed when no approved model is present.

External services modified: none. Production modified: none. Secrets added: none. Backend migration
added: none. The source artifact intentionally excludes toolchains, dependency caches, runner
configuration, build outputs, APKs, logs, databases, environment files, signing material, and other
temporary state.

The final source ZIP SHA-256 is published beside the downloadable archive because a ZIP cannot
contain its own cryptographic digest without changing that digest.

## Declaration

**PHASE 11 = COMPLETE. PHASE 12 has not started.**
