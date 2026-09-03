# Wake Word security boundary

Wake Word is activation, not identity or authority. A detected phrase cannot authenticate a user,
grant Android or Assistant permission, change Risk or sensitivity, disable Safe Mode, satisfy or
replay confirmation, write Memory, create Task authority, call a provider, construct execution
evidence, invoke an Executor, or execute a financial operation.

The activation gate revalidates an existing authenticated session and registered Device at event
time. It rejects wrong-device, expired/revoked-session, locked-screen, stale, future, malformed,
disabled, permission-denied, and power-restricted events before Phase 9. Backend Phase 9 again
enforces session, user, Device, Conversation, AI Router, sensitivity, and revocation boundaries;
local checks are defense in depth, not server authority.

## Microphone and Android policy

Wake is opt-in and disabled after installation. Permission is requested only after the privacy
explanation. The microphone foreground service can be started only from the non-exported app path
after visible user intent; it has a visible ongoing notification and is `START_NOT_STICKY`.
Process death, reboot, update, or a stored preference cannot silently start capture. No boot
receiver, accessibility/overlay abuse, battery-optimization bypass, hidden notification, wake
lock, or background-start workaround exists.

Screen off suspends the detector. Lock-screen wake and sensitive disclosure are unsupported and
fail closed. Power saver, severe thermal state, microphone loss, detector failure, or permission
revocation explicitly suspend/stop capture. Wake listening does not permanently request audio
focus or force a Bluetooth route.

## Local privacy boundary

Before detection, fixed PCM frames enter only the local detector interface. There is no network
client, provider client, speech recognizer, transcript, file output, database entity, analytics
event, log, Audit record, or pre-roll path in the detector. The event produced after detection is
metadata-only. Ambient audio and the wake phrase never become Conversation or Memory.

The shipped default detector is unavailable until a local model is approved. It does not open the
microphone and cannot fall back to cloud STT. A fake engine exists only in test sources and passes
through the same activation policy; it is not an authority bypass or production implementation.

## Duplicate and concurrency defense

At most one detector callback is outstanding. Event/profile/device/time validation precedes the
handoff. The activation ID is durably stored before calling Phase 9. Duplicate IDs, rapid separate
events, stale events, callbacks after disable, and process-recreated retries cannot create a second
session. When Voice is active, Wake suspends and focuses the existing session. Phase 9 turn and
session idempotency remains independent defense in depth.

## Financial and truthful behavior

The phrase and following request are separate. “Hola asistente, confirmo, compra Bitcoin” only
activates Phase 9; the final validated request still traverses Text Assistant, Orchestrator,
Permissions, Risk, Confirmation, Safe Mode, Task, and FinancialExecutionGuard. With no Executor,
no external side effect can occur and the response cannot claim completion.

## Validation limits

Static/common tests validate authority, state transitions, privacy schema, opt-in, replay,
debounce, device/auth/lock/power rejection, single Voice handoff, manifest constraints, and
historical migration hashes. Hardware behavior and model quality are not fabricated:
`REQUIRES ANDROID RUNTIME TEST` and `REQUIRES MODEL TRAINING` remain explicit.
