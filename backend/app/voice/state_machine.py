"""Single deterministic VoiceSession state-transition authority."""

from backend.app.voice.enums import VoiceSessionState

TERMINAL_VOICE_STATES = frozenset({VoiceSessionState.ENDED, VoiceSessionState.FAILED})

_TRANSITIONS: dict[VoiceSessionState, frozenset[VoiceSessionState]] = {
    VoiceSessionState.IDLE: frozenset(
        {VoiceSessionState.CONNECTING, VoiceSessionState.ENDED, VoiceSessionState.FAILED}
    ),
    VoiceSessionState.CONNECTING: frozenset(
        {VoiceSessionState.LISTENING, VoiceSessionState.ENDED, VoiceSessionState.FAILED}
    ),
    VoiceSessionState.LISTENING: frozenset(
        {
            VoiceSessionState.PROCESSING,
            VoiceSessionState.RECONNECTING,
            VoiceSessionState.ENDED,
            VoiceSessionState.FAILED,
        }
    ),
    VoiceSessionState.PROCESSING: frozenset(
        {
            VoiceSessionState.SPEAKING,
            VoiceSessionState.LISTENING,
            VoiceSessionState.RECONNECTING,
            VoiceSessionState.ENDED,
            VoiceSessionState.FAILED,
        }
    ),
    VoiceSessionState.SPEAKING: frozenset(
        {
            VoiceSessionState.INTERRUPTING,
            VoiceSessionState.LISTENING,
            VoiceSessionState.RECONNECTING,
            VoiceSessionState.ENDED,
            VoiceSessionState.FAILED,
        }
    ),
    VoiceSessionState.INTERRUPTING: frozenset(
        {
            VoiceSessionState.LISTENING,
            VoiceSessionState.PROCESSING,
            VoiceSessionState.RECONNECTING,
            VoiceSessionState.ENDED,
            VoiceSessionState.FAILED,
        }
    ),
    VoiceSessionState.RECONNECTING: frozenset(
        {
            VoiceSessionState.CONNECTING,
            VoiceSessionState.LISTENING,
            VoiceSessionState.ENDED,
            VoiceSessionState.FAILED,
        }
    ),
    VoiceSessionState.ENDED: frozenset(),
    VoiceSessionState.FAILED: frozenset(),
}


class InvalidVoiceTransitionError(ValueError):
    """Raised before an invalid or terminal-state transition can be persisted."""


def require_voice_transition(
    current: VoiceSessionState, target: VoiceSessionState
) -> VoiceSessionState:
    if target == current:
        return current
    if target not in _TRANSITIONS[current]:
        raise InvalidVoiceTransitionError(f"Invalid voice transition: {current} -> {target}")
    return target
