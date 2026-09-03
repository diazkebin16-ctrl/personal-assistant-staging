package com.personalassistant.shared

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

const val DefaultWakeProfileId = "local-default-v1"
const val DefaultWakePhrase = "Hola asistente"
const val DefaultWakeRefractoryMillis = 3_000L
const val MaxWakeEventAgeMillis = 5_000L
const val MaxWakePcmFrames = 25

@Serializable
enum class WakeWordState {
    DISABLED,
    ENABLING,
    READY,
    LISTENING,
    DETECTED,
    ACTIVATING,
    SUSPENDED,
    ERROR,
}

@Serializable
enum class WakeWordError {
    OPT_IN_REQUIRED,
    MIC_PERMISSION_DENIED,
    ENGINE_UNAVAILABLE,
    MICROPHONE_UNAVAILABLE,
    AUTH_UNAVAILABLE,
    DEVICE_UNAVAILABLE,
    DEVICE_MISMATCH,
    LOCKED,
    POWER_RESTRICTED,
    MALFORMED_EVENT,
    STALE_EVENT,
    INTERNAL_ERROR,
}

@Serializable
enum class WakeConfidenceBucket { LOW, MEDIUM, HIGH }

@Serializable
data class WakeWordConfig(
    @SerialName("profile_id") val profileId: String = DefaultWakeProfileId,
    @SerialName("display_phrase") val displayPhrase: String = DefaultWakePhrase,
    @SerialName("detector_profile_version") val detectorProfileVersion: String = "untrained-v1",
    @SerialName("confidence_threshold") val confidenceThreshold: Float = 0.80f,
    @SerialName("refractory_millis") val refractoryMillis: Long = DefaultWakeRefractoryMillis,
) {
    init {
        require(profileId.matches(Regex("^[a-z0-9][a-z0-9._-]{2,63}$")))
        require(displayPhrase.length in 3..48)
        require(detectorProfileVersion.matches(Regex("^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")))
        require(confidenceThreshold in 0.50f..0.99f)
        require(refractoryMillis in 1_000L..10_000L)
    }
}

@Serializable
data class WakeWordEvent(
    @SerialName("event_id") val eventId: String,
    @SerialName("device_id") val deviceId: String,
    @SerialName("detected_at_epoch_millis") val detectedAtEpochMillis: Long,
    @SerialName("engine_version") val engineVersion: String,
    @SerialName("detector_profile_version") val detectorProfileVersion: String,
    @SerialName("confidence_bucket") val confidenceBucket: WakeConfidenceBucket? = null,
) {
    init {
        require(WakeActivationIdentity.isValid(eventId))
        require(deviceId.isNotBlank() && deviceId.length <= 256)
        require(detectedAtEpochMillis > 0)
        require(engineVersion.matches(Regex("^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")))
        require(detectorProfileVersion.matches(Regex("^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")))
    }
}

enum class VoiceActivationSource { MANUAL, WAKE_WORD }

data class VoiceActivationRequest(
    val activationId: String,
    val conversationId: String,
    val source: VoiceActivationSource,
)

enum class VoiceActivationOutcome {
    STARTED,
    FOCUSED_EXISTING_SESSION,
    DUPLICATE,
    DEBOUNCED,
    DISABLED,
    AUTH_REQUIRED,
    DEVICE_REQUIRED,
    DEVICE_MISMATCH,
    MIC_PERMISSION_REQUIRED,
    LOCKED,
    POWER_RESTRICTED,
    STALE_EVENT,
    MALFORMED_EVENT,
    FAILED,
}

data class WakeActivationPolicy(
    val optedIn: Boolean,
    val microphonePermissionGranted: Boolean,
    val authenticated: Boolean,
    val registeredDeviceId: String?,
    val deviceUnlocked: Boolean,
    val powerRestricted: Boolean,
)

data class WakeActivationRecord(
    val activationId: String,
    val acceptedAtEpochMillis: Long,
)

data class WakeMetrics(
    val detectionCount: Long = 0,
    val activationCount: Long = 0,
    val duplicateCount: Long = 0,
    val debouncedCount: Long = 0,
    val rejectionCount: Long = 0,
    val detectorRestartCount: Long = 0,
    val lastActivationLatencyMillis: Long? = null,
)

interface WakeActivationStore {
    suspend fun lastAccepted(): WakeActivationRecord?
    suspend fun saveAccepted(record: WakeActivationRecord)
}

interface VoiceActivationGateway {
    fun hasActiveSession(): Boolean
    suspend fun activate(request: VoiceActivationRequest): Boolean
}

interface WakeWordEngine {
    val state: StateFlow<WakeWordState>
    val engineVersion: String
    val profileAvailable: Boolean
    suspend fun start(config: WakeWordConfig, onEvent: suspend (WakeWordEvent) -> Unit)
    suspend fun stop()
    suspend fun suspendListening()
    suspend fun resume(config: WakeWordConfig, onEvent: suspend (WakeWordEvent) -> Unit)
}

class InvalidWakeStateTransition(message: String) : IllegalStateException(message)

class WakeWordStateMachine(initial: WakeWordState = WakeWordState.DISABLED) {
    var state: WakeWordState = initial
        private set

    fun transition(target: WakeWordState): WakeWordState {
        if (target == state) return state
        if (target !in transitions.getValue(state)) {
            throw InvalidWakeStateTransition("Invalid wake transition: $state -> $target")
        }
        state = target
        return state
    }

    private companion object {
        val transitions = mapOf(
            WakeWordState.DISABLED to setOf(WakeWordState.ENABLING),
            WakeWordState.ENABLING to setOf(
                WakeWordState.READY,
                WakeWordState.SUSPENDED,
                WakeWordState.ERROR,
                WakeWordState.DISABLED,
            ),
            WakeWordState.READY to setOf(
                WakeWordState.LISTENING,
                WakeWordState.SUSPENDED,
                WakeWordState.ERROR,
                WakeWordState.DISABLED,
            ),
            WakeWordState.LISTENING to setOf(
                WakeWordState.DETECTED,
                WakeWordState.SUSPENDED,
                WakeWordState.ERROR,
                WakeWordState.DISABLED,
            ),
            WakeWordState.DETECTED to setOf(
                WakeWordState.ACTIVATING,
                WakeWordState.LISTENING,
                WakeWordState.SUSPENDED,
                WakeWordState.ERROR,
                WakeWordState.DISABLED,
            ),
            WakeWordState.ACTIVATING to setOf(
                WakeWordState.LISTENING,
                WakeWordState.SUSPENDED,
                WakeWordState.ERROR,
                WakeWordState.DISABLED,
            ),
            WakeWordState.SUSPENDED to setOf(
                WakeWordState.ENABLING,
                WakeWordState.READY,
                WakeWordState.ERROR,
                WakeWordState.DISABLED,
            ),
            WakeWordState.ERROR to setOf(WakeWordState.ENABLING, WakeWordState.DISABLED),
        )
    }
}

object WakeActivationIdentity {
    private val allowed = Regex("^wake:[A-Za-z0-9][A-Za-z0-9._:-]{7,122}$")
    fun isValid(value: String): Boolean = allowed.matches(value)
    fun requireValid(value: String): String = value.also { require(isValid(it)) }
}

/**
 * Canonical local activation gate. Both manual and wake-word intents converge here before
 * VoiceSessionController; the detector never owns authentication, routing, or transport.
 */
class WakeActivationController(
    private val engine: WakeWordEngine,
    private val voice: VoiceActivationGateway,
    private val store: WakeActivationStore,
    private val policy: suspend () -> WakeActivationPolicy,
    private val clockMillis: () -> Long,
) {
    private val mutex = Mutex()
    private var machine = WakeWordStateMachine()
    private var config = WakeWordConfig()
    private var conversationId: String? = null
    private var eventHandler: suspend (WakeWordEvent) -> Unit = { handleWakeEvent(it) }
    private val _state = MutableStateFlow(WakeWordState.DISABLED)
    val state: StateFlow<WakeWordState> = _state
    private val _error = MutableStateFlow<WakeWordError?>(null)
    val error: StateFlow<WakeWordError?> = _error
    private val _metrics = MutableStateFlow(WakeMetrics())
    val metrics: StateFlow<WakeMetrics> = _metrics

    suspend fun enable(conversationId: String, config: WakeWordConfig): Boolean = mutex.withLock {
        require(conversationId.isNotBlank())
        if (machine.state !in setOf(WakeWordState.DISABLED, WakeWordState.SUSPENDED, WakeWordState.ERROR)) {
            return@withLock machine.state == WakeWordState.LISTENING
        }
        transition(WakeWordState.ENABLING)
        this.config = config
        this.conversationId = conversationId
        val current = policy()
        val rejection = policyRejection(current, expectedDeviceId = null, requireWakeOptIn = true)
        if (rejection != null) {
            fail(WakeWordState.SUSPENDED, rejection.second)
            return@withLock false
        }
        if (!engine.profileAvailable) {
            fail(WakeWordState.ERROR, WakeWordError.ENGINE_UNAVAILABLE)
            return@withLock false
        }
        return@withLock try {
            engine.start(config, eventHandler)
            transition(WakeWordState.READY)
            transition(WakeWordState.LISTENING)
            true
        } catch (_: Exception) {
            engine.stop()
            fail(WakeWordState.ERROR, WakeWordError.MICROPHONE_UNAVAILABLE)
            false
        }
    }

    suspend fun disable() = mutex.withLock {
        engine.stop()
        conversationId = null
        if (machine.state != WakeWordState.DISABLED) transition(WakeWordState.DISABLED)
        _error.value = null
    }

    /** Stops host-owned capture without changing the persisted user preference. */
    suspend fun onHostStopped() = mutex.withLock {
        engine.stop()
        if (machine.state !in setOf(WakeWordState.DISABLED, WakeWordState.ERROR)) {
            transition(WakeWordState.SUSPENDED)
        }
    }

    suspend fun suspendForPolicy(error: WakeWordError) = mutex.withLock {
        engine.suspendListening()
        if (machine.state !in setOf(
                WakeWordState.DISABLED,
                WakeWordState.SUSPENDED,
                WakeWordState.ERROR,
            )
        ) {
            transition(WakeWordState.SUSPENDED)
        }
        _error.value = error
    }

    suspend fun resume(): Boolean = mutex.withLock {
        if (machine.state != WakeWordState.SUSPENDED) return@withLock false
        val target = conversationId ?: return@withLock false
        val current = policy()
        val rejection = policyRejection(current, expectedDeviceId = null, requireWakeOptIn = true)
        if (rejection != null || !engine.profileAvailable) return@withLock false
        return@withLock try {
            transition(WakeWordState.READY)
            engine.resume(config, eventHandler)
            _metrics.value = _metrics.value.copy(
                detectorRestartCount = _metrics.value.detectorRestartCount + 1,
            )
            transition(WakeWordState.LISTENING)
            _error.value = null
            target.isNotBlank()
        } catch (_: Exception) {
            fail(WakeWordState.ERROR, WakeWordError.MICROPHONE_UNAVAILABLE)
            false
        }
    }

    suspend fun activateManual(request: VoiceActivationRequest): VoiceActivationOutcome = mutex.withLock {
        require(request.source == VoiceActivationSource.MANUAL)
        activate(request, expectedDeviceId = null, eventTimeMillis = clockMillis())
    }

    suspend fun handleWakeEvent(event: WakeWordEvent): VoiceActivationOutcome = mutex.withLock {
        if (machine.state != WakeWordState.LISTENING) return@withLock VoiceActivationOutcome.DISABLED
        _metrics.value = _metrics.value.copy(
            detectionCount = _metrics.value.detectionCount + 1,
        )
        if (
            event.detectorProfileVersion != config.detectorProfileVersion ||
            event.engineVersion != engine.engineVersion
        ) {
            return@withLock reject(WakeWordError.MALFORMED_EVENT, VoiceActivationOutcome.MALFORMED_EVENT)
        }
        val now = clockMillis()
        if (event.detectedAtEpochMillis > now + 1_000L || now - event.detectedAtEpochMillis > MaxWakeEventAgeMillis) {
            return@withLock reject(WakeWordError.STALE_EVENT, VoiceActivationOutcome.STALE_EVENT)
        }
        transition(WakeWordState.DETECTED)
        activate(
            VoiceActivationRequest(
                activationId = event.eventId,
                conversationId = conversationId ?: return@withLock reject(
                    WakeWordError.MALFORMED_EVENT,
                    VoiceActivationOutcome.MALFORMED_EVENT,
                ),
                source = VoiceActivationSource.WAKE_WORD,
            ),
            expectedDeviceId = event.deviceId,
            eventTimeMillis = event.detectedAtEpochMillis,
        )
    }

    suspend fun onVoiceSessionEnded() = mutex.withLock {
        if (machine.state != WakeWordState.ACTIVATING) return@withLock
        val current = policy()
        if (policyRejection(current, expectedDeviceId = null, requireWakeOptIn = true) == null && engine.profileAvailable) {
            transition(WakeWordState.SUSPENDED)
            try {
                transition(WakeWordState.READY)
                engine.resume(config, eventHandler)
                _metrics.value = _metrics.value.copy(
                    detectorRestartCount = _metrics.value.detectorRestartCount + 1,
                )
                transition(WakeWordState.LISTENING)
                _error.value = null
            } catch (_: Exception) {
                fail(WakeWordState.ERROR, WakeWordError.MICROPHONE_UNAVAILABLE)
            }
        } else {
            transition(WakeWordState.SUSPENDED)
        }
    }

    private suspend fun activate(
        request: VoiceActivationRequest,
        expectedDeviceId: String?,
        eventTimeMillis: Long,
    ): VoiceActivationOutcome {
        if (!WakeActivationIdentity.isValid(request.activationId) || request.conversationId.isBlank()) {
            return reject(WakeWordError.MALFORMED_EVENT, VoiceActivationOutcome.MALFORMED_EVENT)
        }
        val current = policy()
        policyRejection(
            current,
            expectedDeviceId,
            requireWakeOptIn = request.source == VoiceActivationSource.WAKE_WORD,
            requireWakePower = request.source == VoiceActivationSource.WAKE_WORD,
        )?.let { (state, error) ->
            return reject(error, state)
        }
        if (voice.hasActiveSession()) {
            if (request.source == VoiceActivationSource.WAKE_WORD && machine.state == WakeWordState.DETECTED) {
                engine.suspendListening()
                transition(WakeWordState.ACTIVATING)
            }
            return VoiceActivationOutcome.FOCUSED_EXISTING_SESSION
        }
        val prior = store.lastAccepted()
        if (prior?.activationId == request.activationId) {
            if (request.source == VoiceActivationSource.WAKE_WORD && machine.state == WakeWordState.DETECTED) {
                transition(WakeWordState.LISTENING)
            }
            _metrics.value = _metrics.value.copy(
                duplicateCount = _metrics.value.duplicateCount + 1,
            )
            return VoiceActivationOutcome.DUPLICATE
        }
        if (request.source == VoiceActivationSource.WAKE_WORD &&
            prior != null && eventTimeMillis - prior.acceptedAtEpochMillis < config.refractoryMillis
        ) {
            transition(WakeWordState.LISTENING)
            _metrics.value = _metrics.value.copy(
                debouncedCount = _metrics.value.debouncedCount + 1,
            )
            return VoiceActivationOutcome.DEBOUNCED
        }
        if (request.source == VoiceActivationSource.WAKE_WORD) {
            engine.suspendListening()
            transition(WakeWordState.ACTIVATING)
        }
        // Persist before handoff so duplicate callbacks and process recreation cannot start twice.
        store.saveAccepted(WakeActivationRecord(request.activationId, eventTimeMillis))
        val started = runCatching { voice.activate(request) }.getOrDefault(false)
        if (!started) {
            if (request.source == VoiceActivationSource.WAKE_WORD) {
                transition(WakeWordState.SUSPENDED)
            }
            _error.value = WakeWordError.INTERNAL_ERROR
            return VoiceActivationOutcome.FAILED
        }
        _metrics.value = _metrics.value.copy(
            activationCount = _metrics.value.activationCount + 1,
            lastActivationLatencyMillis = (clockMillis() - eventTimeMillis).coerceAtLeast(0),
        )
        return VoiceActivationOutcome.STARTED
    }

    private fun policyRejection(
        policy: WakeActivationPolicy,
        expectedDeviceId: String?,
        requireWakeOptIn: Boolean,
        requireWakePower: Boolean = true,
    ): Pair<VoiceActivationOutcome, WakeWordError>? = when {
        requireWakeOptIn && !policy.optedIn ->
            VoiceActivationOutcome.DISABLED to WakeWordError.OPT_IN_REQUIRED
        !policy.microphonePermissionGranted ->
            VoiceActivationOutcome.MIC_PERMISSION_REQUIRED to WakeWordError.MIC_PERMISSION_DENIED
        !policy.authenticated -> VoiceActivationOutcome.AUTH_REQUIRED to WakeWordError.AUTH_UNAVAILABLE
        policy.registeredDeviceId == null ->
            VoiceActivationOutcome.DEVICE_REQUIRED to WakeWordError.DEVICE_UNAVAILABLE
        expectedDeviceId != null && expectedDeviceId != policy.registeredDeviceId ->
            VoiceActivationOutcome.DEVICE_MISMATCH to WakeWordError.DEVICE_MISMATCH
        !policy.deviceUnlocked -> VoiceActivationOutcome.LOCKED to WakeWordError.LOCKED
        requireWakePower && policy.powerRestricted ->
            VoiceActivationOutcome.POWER_RESTRICTED to WakeWordError.POWER_RESTRICTED
        else -> null
    }

    private suspend fun reject(
        error: WakeWordError,
        outcome: VoiceActivationOutcome,
    ): VoiceActivationOutcome {
        val suspendCapture = error in setOf(
            WakeWordError.MIC_PERMISSION_DENIED,
            WakeWordError.AUTH_UNAVAILABLE,
            WakeWordError.DEVICE_UNAVAILABLE,
            WakeWordError.DEVICE_MISMATCH,
            WakeWordError.LOCKED,
            WakeWordError.POWER_RESTRICTED,
            WakeWordError.MALFORMED_EVENT,
        )
        if (suspendCapture) {
            engine.suspendListening()
            if (machine.state !in setOf(
                    WakeWordState.DISABLED,
                    WakeWordState.SUSPENDED,
                    WakeWordState.ERROR,
                )
            ) {
                transition(WakeWordState.SUSPENDED)
            }
        } else if (machine.state == WakeWordState.DETECTED) {
            transition(WakeWordState.LISTENING)
        }
        _error.value = error
        _metrics.value = _metrics.value.copy(
            rejectionCount = _metrics.value.rejectionCount + 1,
        )
        return outcome
    }

    private fun fail(target: WakeWordState, error: WakeWordError) {
        transition(target)
        _error.value = error
    }

    private fun transition(target: WakeWordState) {
        machine.transition(target)
        _state.value = machine.state
    }
}

object WakeAuthorityBoundary {
    fun wakeMayAuthenticate(): Boolean = false
    fun wakeMayGrantOsPermission(): Boolean = false
    fun wakeMayGrantAssistantPermission(): Boolean = false
    fun wakeMayConfirm(): Boolean = false
    fun wakeMayChangeRisk(): Boolean = false
    fun wakeMayChangeSensitivity(): Boolean = false
    fun wakeMayDisableSafeMode(): Boolean = false
    fun wakeMayCallProvider(): Boolean = false
    fun wakeMayCallExecutor(): Boolean = false
    fun wakeMayExecuteFinancialAction(): Boolean = false
    fun preWakeAudioMayLeaveDevice(): Boolean = false
    fun preWakeAudioMayBePersisted(): Boolean = false
    fun wakePhraseMayBecomeMemory(): Boolean = false
}
