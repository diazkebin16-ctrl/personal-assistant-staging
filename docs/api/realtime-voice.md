# Realtime Voice API

All control endpoints require the same verified bearer identity and registered `X-Device-ID` used
by the Android Agent. Bodies never accept `user_id`, provider, model, voice profile, sensitivity,
permission, confirmation, Safe Mode, or execution fields. The calm/professional profile is selected
from validated server environment configuration and can change without granting client routing
authority.

## Control endpoints

- `POST /api/v1/voice/sessions` starts a session for an owned Conversation and returns the session
  ID plus short-lived stream credential.
- `POST /api/v1/voice/sessions/{session_id}/credential` rotates the credential for the same owner,
  device, and auth session.
- `POST /api/v1/voice/sessions/{session_id}/end` ends an owned session.
- `WSS /api/v1/voice/sessions/{session_id}/stream` carries bounded voice events. The ephemeral
  token is supplied in `X-Voice-Session-Token`, never in the URL.

Production rejects non-WSS streaming. Credentials expire within 120 seconds by default and are
also capped by the authenticated session expiry.

## Wire semantics

Client events are strict tagged JSON structures for PCM audio frames, interrupt, playback-complete,
or session-end. Frames carry a logical turn ID and consecutive sequence number. Unknown fields,
oversized messages, invalid ordering, cross-turn output, duplicate final events, or malformed
provider events fail closed without echoing private payloads.

Server events describe session state, partial/final transcript, authoritative assistant text,
assistant PCM audio frames, interruption, or a typed error. Partial transcripts are UI-only.
Assistant text and audio are emitted only after a final transcript completes the certified Text
Assistant path. Confirmation-required and unavailable outcomes remain truthful; no event claims an
external action was executed.

There is no raw provider socket, provider credential, force-model, force-provider, raw completion,
tool, confirmation fabrication, action execution, or system-prompt endpoint.
