# Realtime Voice architecture

Phase 9 adds voice as an input/output interface over the certified Text Assistant. It does not
create another assistant or another authority chain. The canonical path is:

1. Compose expresses start, stop, mute, or interrupt intent to one `VoiceSessionController`.
2. The controller obtains a scoped backend `VoiceSession`; Android receives only a short-lived,
   session-bound credential.
3. `AndroidAudioInput` captures bounded PCM16 frames only while that session is active.
4. `OkHttpVoiceTransport` sends frames over authenticated WSS to one backend coordinator.
5. The server-selected realtime provider emits partial and final transcripts.
6. Partial text is UI feedback only. A final transcript is submitted once through Phase 7
   `TextAssistantService`, which retains Memory, Router, Orchestrator, permission, risk,
   confirmation, Safe Mode, Task, and FinancialExecutionGuard boundaries.
7. The authoritative assistant response is streamed as text and provider audio. Android plays it
   through a bounded, cancelable `AudioTrack` path.

There is no UI-to-provider path, foreground microphone service, Executor, Wake Word, parallel
conversation store, Voice Memory engine, or Voice policy engine.

## Module boundary

`mobile/shared` owns portable state, event, error, audio-format, session API, transport, bounded
buffer, and reconnect contracts. `mobile/androidApp` owns microphone permission, `AudioRecord`,
`AudioTrack`, audio focus/routing, WebSocket transport, Compose, and lifecycle. Backend
`app/voice` owns scoped credentials, session/turn persistence, state transitions, protocol
ordering, provider registry, server-configured voice profile, and the final Text Assistant bridge.

The default profile identifier `calm-professional-v1` is a provider-neutral contract. An approved
live adapter must map it to a masculine, calm, professional, assured, natural, lightly futuristic
voice without copying or impersonating an actor or fictional character. `VOICE_PROFILE` can select
another approved server profile without an Android release; the phone cannot provide this value.

## State and session authority

The state machine is explicit: `IDLE`, `CONNECTING`, `LISTENING`, `PROCESSING`, `SPEAKING`,
`INTERRUPTING`, `RECONNECTING`, `ENDED`, and `FAILED`. Invalid transitions fail closed and terminal
states cannot revive. Each server session binds the authenticated user, active registered device,
auth session, conversation, routing decision, and random short-lived credential hash. The client
cannot supply a user, provider, model, sensitivity, or routing decision.

Only the credential hash is persisted. Credential refresh invalidates the previous value. WSS
auth uses a header, not a URI. The backend revalidates user, device, auth-session revocation, TTL,
session duration, conversation ownership, and the current connection lease. Provider secrets are
never issued to Android.

## Sensitivity and provider boundary

Audio meaning is unknown before speech recognition. Phase 9 therefore classifies realtime ingress
conservatively as `CRITICAL`, requires `REALTIME` audio/text capability, and sets `local_only`.
Only AI Router may choose an enabled eligible model. An unavailable approved local model/provider
causes an honest denial; audio is never sent to an arbitrary external provider as a fallback.
The production registry is empty by default. Certification uses an injected local fake through the
same Router and provider contracts, not an authority bypass.

## Audio and turns

The certified format is 24 kHz, mono, signed PCM16, 20 ms frames. Capture and playback buffers are
bounded to 50 frames; the wire parser limits individual events and the Android inbound queue is
bounded. Raw audio stays memory-only and is cleared on stop. Overflow degrades or fails rather
than growing without limit.

Provider VAD/turn events define boundaries; Phase 9 has no hotword detector. Every final turn has
a logical turn ID and deterministic Text Assistant idempotency identity. A repeated final transcript
returns the stored logical result without generating another assistant audio response; changed
content under the same turn ID conflicts. Partials never persist messages, save Memory, create a
Task/workflow, or satisfy confirmation.

## Barge-in, reconnect, and cancellation

Barge-in stops and flushes playback first, increments the playback generation so old frames are
stale, sends one provider interrupt, and returns to listening before processing a new turn. Old
audio cannot resume. User end, app background, screen lock, network failure, provider failure, or
timeout closes microphone, playback, socket, queues, and provider generation.

Reconnect uses at most three attempts, refreshes the expiring session credential, and reconnects
the same server session. The server connection lease and logical turn identity prevent concurrent
streams and duplicate turns. Connection timeout is 10 seconds, idle timeout 45 seconds, credential
TTL 120 seconds, and maximum session duration 15 minutes by default; all are centrally bounded and
environment-configurable.

## Android audio/lifecycle foundation

Microphone permission is requested just in time after an explicit start action. Recording cannot
start without the OS grant or outside an active session. Activity background/screen lock ends the
session unless the Activity is only recreating for a configuration change. There is no background
microphone service or hidden recording.

Playback requests audio focus, releases it on cleanup, and uses Android communication-device
routing foundations for speaker, earpiece, wired, and Bluetooth devices. Focus loss stops playback.
Exact device routing, acoustic behavior, interruption latency, process death, and configuration
changes require emulator/physical-device validation.

## Cost, latency, and continuity

Sockets close at end, idle timeout, maximum duration, or exhausted reconnect. Silence is not
persisted, no duplicate STT/TTS path exists, and duplicate logical turns do not synthesize twice.
Privacy-safe metrics cover connection, turn, reconnect, interrupt, and outcome metadata. Text and
voice alternate in the same Conversation, so visible history and Memory remain one shared system.

## Dependency decision

Phase 9 declares OkHttp 4.12 directly for Android WebSocket lifecycle because Android/KMP standard
libraries provide no secure realtime socket implementation and the existing Ktor HTTP client does
not expose a suitable common WebSocket transport in the offline-certified dependency set. OkHttp is
the mature transport already present transitively through Ktor, so the direct declaration adds no
new runtime binary; it keeps platform-specific networking out of shared core and retains default
TLS verification. Kotlin serialization JSON is also declared directly in the app for strict wire
events; it was already a shared/transitive runtime. Alternatives considered were Ktor WebSockets
(artifact unavailable in the certified lock/cache), raw platform WebSocket APIs (more lifecycle and
parsing code), and WebRTC (unnecessary binary/protocol complexity for this phase). No agent,
analytics, audio SDK, VAD SDK, or live provider SDK was added.

Gradle project-level parallelism is disabled because Room/KSP build variants share one
authoritative schema export and parallel variant processors can race into duplicate generated DAO
sources on a clean multi-variant build. Tasks remain incremental and configuration-cached; this
trades a small build-time cost for deterministic debug/release reproducibility.
