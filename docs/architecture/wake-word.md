# Wake Word architecture

Phase 10 adds a local activation interface in front of the certified Phase 9 voice path. Wake Word
does not authenticate, authorize, confirm, classify content, select a provider, or execute an
action. The only canonical handoff is:

1. a user explicitly opts in from a visible Compose screen;
2. Android grants `RECORD_AUDIO` just in time;
3. a visible microphone foreground service owns one local `AndroidWakeWordEngine`;
4. the engine emits a metadata-only `WakeWordEvent`;
5. `WakeActivationController` revalidates auth, registered Device, screen state, power policy,
   event age, device binding, debounce, and durable activation identity;
6. the controller delegates to the existing `VoiceSessionController`;
7. Phase 9 continues through Realtime Voice and the existing server authority chain.

Manual voice start and Wake Word are separate UI intents but converge at
`WakeActivationController` before any VoiceSession is created. The only Android call to
`VoiceSessionController.start` outside the controller itself is the gateway owned by
`WakeWordManager`. Neither the UI, detector, foreground service, nor engine can open a backend
transport or select a realtime provider.

## KMP and Android boundary

`mobile/shared/WakeContracts.kt` owns the provider-independent states, configuration, event,
errors, authority invariants, activation identity, replay store contract, engine contract, voice
gateway, and canonical controller. It imports no Android API.

`mobile/androidApp/wake` owns `AudioRecord`, the local detector adapter, device preferences,
keyguard/power/permission policy, the user-initiated foreground service, and the gateway to Phase
9. The detector interface accepts fixed PCM16 frames and returns only a confidence bucket. It has
no network, storage, transcript, Memory, provider, or VoiceSession dependency.

## State and event model

The state machine is explicit: `DISABLED`, `ENABLING`, `READY`, `LISTENING`, `DETECTED`,
`ACTIVATING`, `SUSPENDED`, and `ERROR`. Invalid transitions fail. Default state and persisted
preference are disabled. After process recreation, an enabled preference is shown as suspended;
it does not silently restart capture.

A `WakeWordEvent` contains only event ID, registered device ID, timestamp, engine/profile
versions, and an optional coarse confidence bucket. It cannot contain audio or transcript. Events
older than five seconds, materially future-dated, malformed, wrong-profile, or wrong-device fail
closed. The accepted activation identity is committed locally before Phase 9 handoff, so a late or
duplicate callback cannot create another VoiceSession after process recreation.

The default refractory period is three seconds. One detection callback may be outstanding; the
blocking capture loop cannot accumulate callback work. If a Phase 9 session already exists, the
detector is suspended and the existing session keeps focus. No concurrent VoiceSession is created.

## Android policy and foreground service

Target SDK 35 does not permit a normal application to start a microphone foreground service from
arbitrary background state. Phase 10 therefore starts `WakeWordForegroundService` only after the
user chooses Enable in a visible Activity and grants microphone permission. The service is not
exported, declares `foregroundServiceType="microphone"`, posts an ongoing visible notification,
and returns `START_NOT_STICKY`.

There is no `BOOT_COMPLETED` receiver, battery-optimization exemption, overlay, accessibility
service, background-start workaround, hidden notification, or wake lock. Service/process death
closes capture but preserves the preference as suspended. Reboot and app update never enable or
restart the microphone. Screen-off, permission revocation, severe thermal status, or power saver
suspends listening. Unlock or removal of a temporary restriction may resume only while the same
user-initiated service remains alive.

Lock-screen activation is deliberately unsupported in Phase 10. Screen off suspends local
capture, and no sensitive Conversation, Memory, confirmation, or action is exposed while locked.
This is a fail-closed policy, not an authentication substitute.

## VoiceInteractionService evaluation

Android's `VoiceInteractionService` can support a system-selected voice interactor with stronger
OS lifecycle integration. Its benefits are assistant-role integration and system-managed
availability. Its costs are becoming the user's default assistant, a materially different setup
and distribution UX, additional privileged lifecycle/security review, OEM compatibility work, and
long-term maintenance of system voice-interaction contracts.

Phase 10 does not request the assistant role or declare `VoiceInteractionService`. That product
decision is broader than local opt-in Wake Word. The engine/controller contracts remain compatible
with a future OS-owned host adapter without changing VoiceSession, authority, or Conversation.

## Local detector and model decision

Detection is local-first and there is no cloud fallback. No wake SDK was added because the project
has not approved a maintained offline SDK/model, its license/commercial terms, CPU/battery cost,
binary/model size, supported ABIs, security history, or custom-phrase training process. Shipping an
abandoned library or an unreviewed proprietary credential would violate the phase's dependency and
privacy requirements.

The release includes the complete `LocalWakeWordDetector` adapter and bounded AudioRecord engine,
but the safe default detector reports `ENGINE_UNAVAILABLE` and never opens the microphone. Tests
use `FakeWakeWordEngine` only through the same contracts. Enabling a production phrase therefore
requires an approved local model and `REQUIRES MODEL TRAINING`; it cannot fall back to Android
cloud speech recognition or a realtime provider. This limitation is visible to the user.

## Audio, battery, and interruptions

Pre-wake audio is 16 kHz mono PCM16 in fixed 20 ms frames. It is passed directly to the local
detector and is neither retained nor forwarded. There is no pre-roll. A single fixed frame and
bounded detection-pending flag prevent buffer growth. Blocking reads avoid polling; no wake lock or
permanent audio focus is taken.

AudioRecord failure, microphone removal/contention, permission revocation, service destruction,
power saver, thermal restriction, disable, or logout stops/suspends capture. Incoming-call and
device-route behavior relies on Android audio ownership and must be validated on hardware.
Bluetooth/headset microphones are not forced; Phase 9 retains post-activation routing authority.

## Privacy, logging, and telemetry

Raw audio, audio fingerprints, ambient transcripts, wake recordings, Memory, and provider
credentials are not persisted or logged. Safe future metrics may include event ID, engine/profile
version, state, activation outcome, latency, error category, restart count, coarse confidence,
CPU/battery foundation, and false-activation counters. No cloud training or audio analytics exists.

## Runtime requirements

Real microphone capture, foreground/background transitions, notification behavior, process death,
screen lock, permission revocation, incoming calls, wired/Bluetooth routing, power saver, thermal
behavior, CPU/battery cost, and false-positive/negative tuning are `REQUIRES ANDROID RUNTIME TEST`.
An approved production wake model is `REQUIRES MODEL TRAINING`. Phase 10 performs no backend,
database, RLS, production, provider, or external-service change.
