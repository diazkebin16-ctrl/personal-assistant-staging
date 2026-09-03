# Phase 8 Android Agent certification scope

Version: 0.8.1

The certification target is the first authenticated, persistent, capability-aware Android client.
It includes the KMP contract/client layer, Keystore-backed identity/session storage, server Device
registration, Text Assistant conversation UI, connectivity state, encrypted Room cache, bounded
WorkManager delivery, stable idempotency, and security/release configuration.

Backend phases 0–7 and migrations 0001–0008 remain unchanged except the application version,
documentation, CI, and additive Phase 8 tests. No `0009` migration is created because the existing
Device and Text Assistant schemas provide the required server persistence.

Local certification covers Python regression, KMP/JVM unit tests, Android compilation/unit tests,
lint, debug and release builds, manifest/network inspection, dependency reports, secret scans, and
archive hygiene when the Android SDK is available. Emulator/device behavior is reported as
`REQUIRES ANDROID RUNTIME TEST`; live Supabase/RLS/JWT/revocation is `REQUIRES STAGING`.

Final local results:

- Backend regression: 658/658 passed; security subset: 194/194 collected and passed.
- Shared KMP/JVM: 29/29 passed, including the authenticated device-to-conversation flow.
- Android local unit tests: 13/13 passed.
- Android lint: no issues; debug and minified production-release builds: passed.
- Migration upgrade, downgrade/re-upgrade, and drift validation: passed.
- Historical migrations `0001`–`0008`: byte-identical to the certified baseline.
- Python and Gradle lockfile vulnerability scans: no known vulnerabilities.
- Security findings: zero critical, high, medium, or low findings.
