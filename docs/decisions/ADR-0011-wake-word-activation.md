# ADR-0011: Local opt-in Wake Word activation

- Status: Accepted
- Date: 2026-09-02

## Context

Phase 10 needs hands-free activation without treating speech as identity or authority, streaming
ambient audio, bypassing Android background-microphone policy, duplicating Phase 9 VoiceSession,
or committing to an unreviewed wake SDK/model. Android target SDK 35 permits ongoing microphone use
for a normal app only under explicit user initiation and a correctly declared, visible microphone
foreground service. `VoiceInteractionService` offers deeper system integration but implies the
default-assistant role and a broader product/distribution commitment.

## Decision

Use one KMP `WakeActivationController` before the existing `VoiceSessionController`. Manual and
wake intents converge there. Host local detection in a non-exported, user-started,
`START_NOT_STICKY` microphone foreground service with a visible notification. Suspend on screen
off, permission loss, power saver, severe thermal state, service death, or detector failure. Never
start from boot or process recreation.

Keep the detector vendor/model behind `LocalWakeWordDetector`. Add no wake SDK until its offline
privacy, maintenance, license, commercial terms, security, ABI, model size, CPU, battery, and
custom-phrase requirements are approved. Ship an unavailable fail-closed detector and test the
entire activation architecture with a fake local engine. Do not use cloud speech recognition as a
wake detector. Defer `VoiceInteractionService` and the assistant role.

## Consequences

- Phase 9, Conversation, Memory, Router, Orchestrator, Confirmation, Safe Mode, Task, and the
  financial guard remain single authorities.
- Pre-wake audio remains local, transient, untranscribed, and unpersisted.
- Activation is visible, opt-in, device-specific, replay-resistant, and policy-compliant.
- Lock-screen activation is unsupported and fails closed.
- Production phrase detection requires an approved local model and model training.
- Real lifecycle, battery, thermal, routing, and detection quality need Android hardware testing.
