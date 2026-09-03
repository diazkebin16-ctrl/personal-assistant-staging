# ADR-0009: KMP contracts with Android-native platform services

Status: Accepted for Phase 8

## Context

The assistant needs a maintainable Android client today and portable domain/API semantics for
future device clients. Forcing Android APIs into shared code would make platform security and
lifecycle behavior opaque; avoiding shared code entirely would duplicate contract and truthful
state rules later.

## Decision

Use a small Kotlin Multiplatform `shared` module for contracts, serialization, typed HTTP,
idempotency/retry rules, errors, capability semantics, and truth-preserving response mapping. Keep
Keystore, Room, WorkManager, ConnectivityManager, OS permissions, Compose, and lifecycle in the
native Android application. Use manual composition because the dependency graph is small and no DI
framework is justified.

Use Room only for structured encrypted cache and durable delivery state. It does not reproduce
server Memory or Task Engine. Reuse the certified Phase 1 Device table; no backend schema or
`0009_android_agent` migration is necessary.

## Consequences

The boundary is testable on JVM and Android, future KMP clients can reuse neutral contracts, and
platform-sensitive behavior remains explicit. Two modules and a small set of mature Jetpack/Kotlin
dependencies add manageable APK/build cost. A full offline system and device attestation remain
deferred rather than being partially invented in Phase 8.

