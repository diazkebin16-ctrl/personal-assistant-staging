# ADR-0010: Realtime Voice as a local-only classified Text Assistant interface

Status: Accepted for Phase 9

## Context

Realtime microphone audio has unknown semantic sensitivity before transcription. Allowing Android
to choose a provider, embedding a provider key, or classifying the stream after an external
provider receives it would violate the certified Router and sensitivity boundaries. A separate
Voice assistant path would also duplicate Conversation, Memory, and action authority.

## Decision

Use one Android `VoiceSessionController`, one authenticated backend WebSocket coordinator, and one
server-selected provider connection. Route unknown audio as `CRITICAL` plus `local_only` through AI
Router. Persist scoped session/turn metadata and bridge exactly one final transcript into the
existing Text Assistant using stable turn idempotency. Partial transcripts remain UI-only. The
provider registry ships empty; a local fake is injected through the same contracts for
certification. Enable a live adapter only after approved server configuration and staging/real-
provider validation.

Android uses mature OkHttp WebSocket support already present in the dependency graph. Portable KMP
contracts remain transport-neutral; Android microphone, playback, focus, routing, permission, and
lifecycle behavior stay in the native module.

## Consequences

- No provider secret or routing authority reaches Android.
- Unknown audio cannot leak to an unauthorized external provider.
- Voice and text share Conversation, Memory semantics, truthful outcomes, and the complete action
  authority chain.
- Production voice is honestly unavailable until an approved local realtime route is configured.
- Hardware behavior and live-provider interoperability require runtime/staging certification.
- Wake Word, always-listening service, Executor, and Phase 10 remain outside scope.

## Alternatives rejected

- Direct Android-to-provider credentials: excessive credential and routing authority.
- External provider before classification: cannot conservatively enforce CRITICAL policy.
- Separate STT plus unrelated TTS pipelines: duplicates processing/cost without a certified need.
- UI-owned socket and service-owned socket: creates competing session authority paths.
- Local Wake Word or foreground microphone service: Phase 10 scope and unnecessary background
  capture.
