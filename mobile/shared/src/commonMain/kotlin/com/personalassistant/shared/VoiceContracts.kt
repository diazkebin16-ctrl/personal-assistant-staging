package com.personalassistant.shared

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

const val VoiceSampleRateHz = 24_000
const val VoiceChannels = 1
const val VoiceFrameDurationMillis = 20
const val VoiceFrameBytes = 960
const val MaxVoiceFrameBytes = 3_840
const val MaxBufferedVoiceFrames = 50

@Serializable
enum class VoiceSessionState {
    IDLE,
    CONNECTING,
    LISTENING,
    PROCESSING,
    SPEAKING,
    INTERRUPTING,
    RECONNECTING,
    ENDED,
    FAILED,
}

@Serializable
enum class TranscriptKind { PARTIAL, FINAL }

@Serializable
enum class VoiceClientEventType { AUDIO_FRAME, INTERRUPT, END_SESSION, PLAYBACK_COMPLETED }

@Serializable
enum class VoiceServerEventType {
    SESSION_STATE,
    TRANSCRIPT,
    ASSISTANT_TEXT,
    ASSISTANT_AUDIO,
    TURN_INTERRUPTED,
    ERROR,
}

@Serializable
enum class VoiceErrorCode {
    MIC_PERMISSION_DENIED,
    AUDIO_DEVICE_UNAVAILABLE,
    NETWORK_UNAVAILABLE,
    VOICE_SESSION_AUTH_FAILED,
    PROVIDER_UNAVAILABLE,
    REALTIME_MODEL_UNAVAILABLE,
    SENSITIVITY_DENIED,
    CONTEXT_LIMIT,
    AUDIO_INPUT_FAILURE,
    AUDIO_OUTPUT_FAILURE,
    SESSION_TIMEOUT,
    RECONNECT_EXHAUSTED,
    MALFORMED_EVENT,
    CANCELLED,
    INTERNAL_ERROR,
}

@Serializable
data class VoiceAudioFormat(
    val encoding: String = "PCM_S16LE",
    @SerialName("sample_rate_hz") val sampleRateHz: Int = VoiceSampleRateHz,
    val channels: Int = VoiceChannels,
    @SerialName("frame_duration_ms") val frameDurationMillis: Int = VoiceFrameDurationMillis,
)

@Serializable
data class VoiceSessionCreateRequest(
    @SerialName("conversation_id") val conversationId: String,
)

@Serializable
data class VoiceSessionResponse(
    val id: String,
    @SerialName("conversation_id") val conversationId: String,
    val state: VoiceSessionState,
    @SerialName("audio_format") val audioFormat: VoiceAudioFormat,
    @SerialName("stream_path") val streamPath: String,
    val credential: String,
    @SerialName("credential_expires_at") val credentialExpiresAt: String,
    @SerialName("idle_timeout_seconds") val idleTimeoutSeconds: Int,
    @SerialName("max_session_seconds") val maxSessionSeconds: Int,
    @SerialName("max_reconnect_attempts") val maxReconnectAttempts: Int,
    @SerialName("started_at") val startedAt: String,
)

@Serializable
data class VoiceSessionCredentialResponse(
    @SerialName("session_id") val sessionId: String,
    val credential: String,
    @SerialName("credential_expires_at") val credentialExpiresAt: String,
)

@Serializable
data class VoiceSessionStateResponse(
    @SerialName("session_id") val sessionId: String,
    val state: VoiceSessionState,
)

@Serializable
data class VoiceClientEvent(
    val type: VoiceClientEventType,
    @SerialName("turn_id") val turnId: String? = null,
    val sequence: Int? = null,
    @SerialName("audio_b64") val audioBase64: String? = null,
)

@Serializable
data class VoiceServerEvent(
    val type: VoiceServerEventType,
    val state: VoiceSessionState? = null,
    @SerialName("turn_id") val turnId: String? = null,
    @SerialName("transcript_kind") val transcriptKind: TranscriptKind? = null,
    val text: String? = null,
    val confidence: Double? = null,
    @SerialName("audio_b64") val audioBase64: String? = null,
    @SerialName("audio_sequence") val audioSequence: Int? = null,
    @SerialName("audio_final") val audioFinal: Boolean? = null,
    val outcome: String? = null,
    @SerialName("confirmation_request_id") val confirmationRequestId: String? = null,
    val error: VoiceErrorCode? = null,
)

data class VoiceAudioFrame(
    val turnId: String,
    val sequence: Int,
    val bytes: ByteArray,
) {
    init {
        require(VoiceTurnIdentity.isValid(turnId))
        require(sequence >= 0)
        require(bytes.isNotEmpty() && bytes.size <= MaxVoiceFrameBytes && bytes.size % 2 == 0)
    }
}

class BoundedVoiceBuffer(private val capacity: Int = MaxBufferedVoiceFrames) {
    private val frames = ArrayDeque<VoiceAudioFrame>()

    init {
        require(capacity in 1..MaxBufferedVoiceFrames)
    }

    val size: Int get() = frames.size

    fun offer(frame: VoiceAudioFrame): Boolean {
        if (frames.size >= capacity) return false
        frames.addLast(frame)
        return true
    }

    fun poll(): VoiceAudioFrame? = frames.removeFirstOrNull()

    fun clear() = frames.clear()
}

object VoiceTurnIdentity {
    private val allowed = Regex("^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")

    fun isValid(value: String): Boolean = allowed.matches(value)
    fun requireValid(value: String): String = value.also { require(isValid(it)) }
}

class InvalidVoiceStateTransition(message: String) : IllegalStateException(message)

class VoiceStateMachine(initial: VoiceSessionState = VoiceSessionState.IDLE) {
    var state: VoiceSessionState = initial
        private set

    fun transition(target: VoiceSessionState): VoiceSessionState {
        if (target == state) return state
        if (target !in transitions.getValue(state)) {
            throw InvalidVoiceStateTransition("Invalid voice transition: $state -> $target")
        }
        state = target
        return state
    }

    private companion object {
        val transitions = mapOf(
            VoiceSessionState.IDLE to setOf(
                VoiceSessionState.CONNECTING,
                VoiceSessionState.ENDED,
                VoiceSessionState.FAILED,
            ),
            VoiceSessionState.CONNECTING to setOf(
                VoiceSessionState.LISTENING,
                VoiceSessionState.ENDED,
                VoiceSessionState.FAILED,
            ),
            VoiceSessionState.LISTENING to setOf(
                VoiceSessionState.PROCESSING,
                VoiceSessionState.RECONNECTING,
                VoiceSessionState.ENDED,
                VoiceSessionState.FAILED,
            ),
            VoiceSessionState.PROCESSING to setOf(
                VoiceSessionState.SPEAKING,
                VoiceSessionState.LISTENING,
                VoiceSessionState.RECONNECTING,
                VoiceSessionState.ENDED,
                VoiceSessionState.FAILED,
            ),
            VoiceSessionState.SPEAKING to setOf(
                VoiceSessionState.INTERRUPTING,
                VoiceSessionState.LISTENING,
                VoiceSessionState.RECONNECTING,
                VoiceSessionState.ENDED,
                VoiceSessionState.FAILED,
            ),
            VoiceSessionState.INTERRUPTING to setOf(
                VoiceSessionState.LISTENING,
                VoiceSessionState.PROCESSING,
                VoiceSessionState.RECONNECTING,
                VoiceSessionState.ENDED,
                VoiceSessionState.FAILED,
            ),
            VoiceSessionState.RECONNECTING to setOf(
                VoiceSessionState.CONNECTING,
                VoiceSessionState.LISTENING,
                VoiceSessionState.ENDED,
                VoiceSessionState.FAILED,
            ),
            VoiceSessionState.ENDED to emptySet(),
            VoiceSessionState.FAILED to emptySet(),
        )
    }
}

data class VoiceReconnectPolicy(
    val maxAttempts: Int = 3,
    val baseDelayMillis: Long = 500,
    val maxDelayMillis: Long = 4_000,
) {
    init {
        require(maxAttempts in 0..3)
        require(baseDelayMillis in 100..2_000)
        require(maxDelayMillis in baseDelayMillis..10_000)
    }

    fun delayMillis(attempt: Int): Long {
        require(attempt in 1..maxAttempts)
        return (baseDelayMillis * (1L shl (attempt - 1))).coerceAtMost(maxDelayMillis)
    }
}

sealed interface VoiceUiState {
    data object Idle : VoiceUiState
    data object Connecting : VoiceUiState
    data class Listening(val partialTranscript: String? = null) : VoiceUiState
    data object Processing : VoiceUiState
    data object Speaking : VoiceUiState
    data object Interrupting : VoiceUiState
    data class Reconnecting(val attempt: Int) : VoiceUiState
    data class WaitingConfirmation(val message: String) : VoiceUiState
    data class WaitingPermission(val message: String) : VoiceUiState
    data class Unavailable(val message: String) : VoiceUiState
    data class Failed(val error: VoiceErrorCode) : VoiceUiState
}

interface VoiceTransport {
    suspend fun connect(streamUrl: String, credential: String)
    suspend fun send(event: VoiceClientEvent)
    suspend fun receive(): VoiceServerEvent?
    suspend fun close()
}

object VoiceAuthorityBoundary {
    fun transcriptMayEnterAssistant(kind: TranscriptKind): Boolean = kind == TranscriptKind.FINAL
    fun partialMayWriteMemory(): Boolean = false
    fun partialMayCreateTask(): Boolean = false
    fun partialMayConfirm(): Boolean = false
    fun voiceMayGrantAssistantPermission(): Boolean = false
    fun voiceMayGrantOsPermission(): Boolean = false
    fun voiceMayChangeRisk(): Boolean = false
    fun voiceMayDisableSafeMode(): Boolean = false
    fun voiceMayFabricateConfirmation(): Boolean = false
    fun voiceMayExecuteFinancialAction(): Boolean = false
}
