# Realtime Voice security boundary

Voice is untrusted input and an interface, not authority. Spoken text and provider output cannot
grant Android or Assistant permissions, change risk, disable Safe Mode, fabricate confirmation,
select a provider/model, lower sensitivity, mutate Memory/Task state, construct an authorized
envelope, or execute a side effect. Final actionable speech follows the same Orchestrator chain as
text. Financial buy, sell, transfer, withdrawal, deposit, order, leverage, and risk-increase
requests remain hard-denied even when the user says they confirm.

## Microphone and credentials

Android requests `RECORD_AUDIO` only after explicit start. No startup request, background listener,
foreground microphone service, hotword, or Wake Word exists. Capture stops on end, cancellation,
failure, background/screen lock, focus/lifecycle cleanup, or controller disposal.

Android contains no provider key, OpenAI key, service-role key, backend secret, or long-lived
voice credential. Backend session evidence is random, short-lived, device/user/auth-session/
conversation scoped, rotated for reconnect, transmitted in a WSS header, persisted only as SHA-256,
and revalidated against revocation. TLS verification uses OkHttp defaults; release rejects
cleartext and does not install a trust-all verifier.

## Content, transcript, and storage

Raw PCM is held only in bounded memory buffers and is never written to disk, analytics, Audit,
telemetry, crash metadata, or logs. Raw transcript, Memory, prompts, and assistant content are also
excluded from operational metadata. The existing owner-scoped Conversation remains the sole
history store; `voice_turns` retains only a transcript hash, confidence, identities, and message
references for idempotency. Conversation history never becomes Memory automatically.

Partial STT is explicitly non-authoritative. Only one validated final transcript enters Text
Assistant. Text Assistant then controls explicit Memory commands, sensitivity, Router invocation,
Orchestrator use, and truthful outcomes. Unknown pre-STT audio is `CRITICAL`/local-only and fails
closed when an authorized local realtime route is unavailable.

## Persistence, RLS, and concurrency

`voice_sessions` and `voice_turns` use ownership FKs, state/value constraints, connection leases,
row locking, optimistic versions, and unique `(session, logical_turn_id)` plus `(user,
idempotency_key)` constraints. `0009_realtime_voice` enables and forces RLS, revokes all `anon` and
`authenticated` privileges, and adds no direct client policy. Voice authority metadata is backend-
only; access occurs through verified API ownership checks. Static and pgTAP definitions validate
this design; real Supabase behavior requires staging.

## Truth, audit, and observability

Spoken responses are synthesized only from the certified `AssistantOutcome`. Waiting permission,
waiting confirmation, Safe Mode, unsupported, denied, or no-Executor outcomes cannot render or
speak as completed. Barge-in invalidates old playback and reconnect never replays completed audio.

Security/governance audit remains in the existing Router, Memory, Orchestrator, Permissions,
Confirmation, and Financial Guard authorities. Voice does not duplicate their audit logic or store
a transcript in Audit. Voice observability is limited to session/conversation/turn identifiers,
state, latency foundation, reconnect/interrupt counts, provider outcome, and high-level error
category. Credentials, auth headers, content, and audio are prohibited.

## Validation limits

Local unit/static validation cannot certify hardware microphone/speaker behavior, audio focus and
Bluetooth routing, actual barge-in latency, OS process death, screen lock behavior, or packaged APK
behavior on a device. Those are `REQUIRES ANDROID RUNTIME TEST`. Live Supabase RLS/JWT/revocation
is `REQUIRES STAGING`. No live realtime adapter is enabled, so provider interoperability, real
latency, VAD, audio quality, cost, and ephemeral provider behavior are `REQUIRES REAL PROVIDER
TEST`.
