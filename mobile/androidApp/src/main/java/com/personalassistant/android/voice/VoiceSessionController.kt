package com.personalassistant.android.voice

import android.util.Base64
import com.personalassistant.shared.ApiResult
import com.personalassistant.shared.BackendApiClient
import com.personalassistant.shared.MaxBufferedVoiceFrames
import com.personalassistant.shared.MaxVoiceFrameBytes
import com.personalassistant.shared.TranscriptKind
import com.personalassistant.shared.VoiceAudioFrame
import com.personalassistant.shared.VoiceClientEvent
import com.personalassistant.shared.VoiceClientEventType
import com.personalassistant.shared.VoiceErrorCode
import com.personalassistant.shared.VoiceReconnectPolicy
import com.personalassistant.shared.VoiceServerEvent
import com.personalassistant.shared.VoiceServerEventType
import com.personalassistant.shared.VoiceSessionCreateRequest
import com.personalassistant.shared.VoiceSessionResponse
import com.personalassistant.shared.VoiceSessionState
import com.personalassistant.shared.VoiceStateMachine
import com.personalassistant.shared.VoiceTransport
import com.personalassistant.shared.VoiceTurnIdentity
import com.personalassistant.shared.VoiceUiState
import java.util.UUID
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.selects.select

class VoiceSessionController(
    private val backend: BackendApiClient,
    private val transportFactory: () -> VoiceTransport,
    private val audioInput: AndroidAudioInput,
    private val audioOutput: AndroidAudioOutput,
    private val scope: CoroutineScope,
    private val onConversationChanged: suspend (String) -> Unit = {},
    private val reconnectPolicy: VoiceReconnectPolicy = VoiceReconnectPolicy(),
) {
    private val _uiState = MutableStateFlow<VoiceUiState>(VoiceUiState.Idle)
    val uiState: StateFlow<VoiceUiState> = _uiState
    private val _muted = MutableStateFlow(false)
    val muted: StateFlow<Boolean> = _muted
    private var machine = VoiceStateMachine()
    private var session: VoiceSessionResponse? = null
    private var transport: VoiceTransport? = null
    private var connectionJob: Job? = null
    private var senderJob: Job? = null
    private var cleanupJob: Job? = null
    private var ending = false
    private var currentTurnId = newTurnId()
    private var audioSequence = 0
    private var pendingOutcomeState: VoiceUiState? = null
    private var lastInterruptedTurnId: String? = null
    private val controlEvents = Channel<VoiceClientEvent>(capacity = 8)
    private val audioFrames = Channel<VoiceAudioFrame>(capacity = MaxBufferedVoiceFrames)
    private val captureLock = Any()

    fun start(conversationId: String, microphonePermissionGranted: Boolean) {
        if (!microphonePermissionGranted) {
            _uiState.value = VoiceUiState.Failed(VoiceErrorCode.MIC_PERMISSION_DENIED)
            return
        }
        if (connectionJob?.isActive == true || cleanupJob?.isActive == true) return
        machine = VoiceStateMachine()
        machine.transition(VoiceSessionState.CONNECTING)
        _uiState.value = VoiceUiState.Connecting
        ending = false
        currentTurnId = newTurnId()
        audioSequence = 0
        pendingOutcomeState = null
        lastInterruptedTurnId = null
        connectionJob = scope.launch {
            when (val result = backend.startVoiceSession(VoiceSessionCreateRequest(conversationId))) {
                is ApiResult.Success -> {
                    session = result.value
                    connectionLoop(result.value.credential)
                }
                is ApiResult.Failure -> fail(result.toVoiceError())
            }
        }
    }

    fun toggleMute() {
        _muted.value = !_muted.value
        if (_muted.value) {
            audioInput.stop()
            drainAudioFrames()
        } else if (machine.state == VoiceSessionState.LISTENING) {
            startCapture()
        }
    }

    fun interruptAssistant() {
        if (machine.state != VoiceSessionState.SPEAKING) return
        val interruptedTurn = currentTurnId
        lastInterruptedTurnId = interruptedTurn
        audioOutput.stopImmediate()
        machine.transition(VoiceSessionState.INTERRUPTING)
        _uiState.value = VoiceUiState.Interrupting
        controlEvents.trySend(
            VoiceClientEvent(
                type = VoiceClientEventType.INTERRUPT,
                turnId = interruptedTurn,
            ),
        )
        machine.transition(VoiceSessionState.LISTENING)
        beginNewTurn()
        _uiState.value = VoiceUiState.Listening()
    }

    fun end() {
        if (ending) return
        ending = true
        cleanupJob = scope.launch {
            val activeSession = session
            runCatching {
                transport?.send(VoiceClientEvent(type = VoiceClientEventType.END_SESSION))
            }
            stopLocalResources()
            if (activeSession != null) backend.endVoiceSession(activeSession.id)
            if (machine.state !in setOf(VoiceSessionState.ENDED, VoiceSessionState.FAILED)) {
                machine.transition(VoiceSessionState.ENDED)
            }
            session = null
            _uiState.value = VoiceUiState.Idle
            cleanupJob = null
        }
    }

    fun onAppBackgrounded() = end()

    private suspend fun connectionLoop(initialCredential: String) {
        var credential = initialCredential
        var reconnectAttempt = 0
        while (!ending) {
            val activeSession = session ?: return
            val activeTransport = transportFactory()
            transport = activeTransport
            try {
                activeTransport.connect(
                    backend.voiceStreamUrl(activeSession.streamPath),
                    credential,
                )
                coroutineScope {
                    senderJob = launch { sendLoop(activeTransport) }
                    startCapture()
                    receiveLoop(activeTransport)
                    senderJob?.cancelAndJoin()
                }
                if (ending) return
                throw IllegalStateException("Voice socket ended unexpectedly")
            } catch (_: Exception) {
                senderJob?.cancel()
                senderJob = null
                audioInput.stop()
                audioOutput.stopImmediate()
                drainAudioFrames()
                runCatching { activeTransport.close() }
                if (ending) return
                if (machine.state == VoiceSessionState.CONNECTING) {
                    fail(VoiceErrorCode.NETWORK_UNAVAILABLE)
                    return
                }
                if (reconnectAttempt >= minOf(
                        reconnectPolicy.maxAttempts,
                        activeSession.maxReconnectAttempts,
                    )
                ) {
                    fail(VoiceErrorCode.RECONNECT_EXHAUSTED)
                    return
                }
                if (machine.state !in setOf(VoiceSessionState.RECONNECTING, VoiceSessionState.FAILED)) {
                    machine.transition(VoiceSessionState.RECONNECTING)
                }
                reconnectAttempt += 1
                _uiState.value = VoiceUiState.Reconnecting(reconnectAttempt)
                delay(reconnectPolicy.delayMillis(reconnectAttempt))
                when (val refreshed = backend.refreshVoiceCredential(activeSession.id)) {
                    is ApiResult.Success -> credential = refreshed.value.credential
                    is ApiResult.Failure -> {
                        if (!refreshed.retryable) {
                            fail(refreshed.toVoiceError())
                            return
                        }
                    }
                }
                beginNewTurn()
            }
        }
    }

    private suspend fun receiveLoop(activeTransport: VoiceTransport) {
        while (!ending) {
            val event = activeTransport.receive() ?: return
            handleServerEvent(event)
        }
    }

    private suspend fun sendLoop(activeTransport: VoiceTransport) {
        while (!ending) {
            select<Unit> {
                controlEvents.onReceive { activeTransport.send(it) }
                audioFrames.onReceive { frame ->
                    activeTransport.send(
                        VoiceClientEvent(
                            type = VoiceClientEventType.AUDIO_FRAME,
                            turnId = frame.turnId,
                            sequence = frame.sequence,
                            audioBase64 = Base64.encodeToString(frame.bytes, Base64.NO_WRAP),
                        ),
                    )
                }
            }
        }
    }

    private fun handleServerEvent(event: VoiceServerEvent) {
        when (event.type) {
            VoiceServerEventType.SESSION_STATE -> event.state?.let(::applyServerState)
            VoiceServerEventType.TRANSCRIPT -> {
                if (event.turnId != currentTurnId) fail(VoiceErrorCode.MALFORMED_EVENT)
                else handleTranscript(event)
            }
            VoiceServerEventType.ASSISTANT_TEXT -> {
                if (event.turnId != currentTurnId) return fail(VoiceErrorCode.MALFORMED_EVENT)
                val message = event.text ?: "No puedo completar eso."
                pendingOutcomeState = when (event.outcome) {
                    "ACTION_WAITING_CONFIRMATION", "MEMORY_CONFIRMATION_REQUIRED" ->
                        VoiceUiState.WaitingConfirmation(message)
                    "ACTION_WAITING_PERMISSION", "MEMORY_PERMISSION_REQUIRED" ->
                        VoiceUiState.WaitingPermission(message)
                    "ACTION_READY_FOR_FUTURE_EXECUTION", "ACTION_UNSUPPORTED", "ACTION_DENIED",
                    "FAILED",
                    -> VoiceUiState.Unavailable(message)
                    else -> null
                }
                session?.conversationId?.let { conversationId ->
                    scope.launch { onConversationChanged(conversationId) }
                }
            }
            VoiceServerEventType.ASSISTANT_AUDIO -> handleAssistantAudio(event)
            VoiceServerEventType.TURN_INTERRUPTED -> {
                if (event.turnId != lastInterruptedTurnId) fail(VoiceErrorCode.MALFORMED_EVENT)
                else lastInterruptedTurnId = null
            }
            VoiceServerEventType.ERROR -> fail(event.error ?: VoiceErrorCode.INTERNAL_ERROR)
        }
    }

    private fun handleTranscript(event: VoiceServerEvent) {
        when (event.transcriptKind) {
            TranscriptKind.PARTIAL -> {
                if (machine.state == VoiceSessionState.LISTENING) {
                    _uiState.value = VoiceUiState.Listening(event.text)
                }
            }
            TranscriptKind.FINAL -> {
                if (machine.state == VoiceSessionState.LISTENING) {
                    machine.transition(VoiceSessionState.PROCESSING)
                    _uiState.value = VoiceUiState.Processing
                }
            }
            null -> fail(VoiceErrorCode.MALFORMED_EVENT)
        }
    }

    private fun handleAssistantAudio(event: VoiceServerEvent) {
        val turnId = event.turnId ?: return fail(VoiceErrorCode.MALFORMED_EVENT)
        if (turnId != currentTurnId) return fail(VoiceErrorCode.MALFORMED_EVENT)
        val audio = event.audioBase64?.let {
            runCatching { Base64.decode(it, Base64.DEFAULT) }.getOrNull()
        }
            ?: return fail(VoiceErrorCode.MALFORMED_EVENT)
        if (audio.isEmpty() || audio.size > MaxVoiceFrameBytes || audio.size % 2 != 0) {
            return fail(VoiceErrorCode.MALFORMED_EVENT)
        }
        if (machine.state == VoiceSessionState.PROCESSING) {
            machine.transition(VoiceSessionState.SPEAKING)
        }
        if (machine.state != VoiceSessionState.SPEAKING) {
            return fail(VoiceErrorCode.MALFORMED_EVENT)
        }
        _uiState.value = VoiceUiState.Speaking
        val accepted = audioOutput.offer(
            turnId = turnId,
            sequence = event.audioSequence ?: 0,
            bytes = audio,
            final = event.audioFinal == true,
            onComplete = { completedTurn ->
                controlEvents.trySend(
                    VoiceClientEvent(
                        type = VoiceClientEventType.PLAYBACK_COMPLETED,
                        turnId = completedTurn,
                    ),
                )
            },
            onFailure = { fail(VoiceErrorCode.AUDIO_OUTPUT_FAILURE) },
            onFocusLost = { interruptAssistant() },
        )
        if (!accepted) fail(VoiceErrorCode.AUDIO_OUTPUT_FAILURE)
    }

    private fun applyServerState(target: VoiceSessionState) {
        if (target == machine.state) return
        runCatching { machine.transition(target) }.onFailure {
            fail(VoiceErrorCode.MALFORMED_EVENT)
            return
        }
        when (target) {
            VoiceSessionState.LISTENING -> {
                val truthfulOutcome = pendingOutcomeState
                pendingOutcomeState = null
                beginNewTurn()
                _uiState.value = truthfulOutcome ?: VoiceUiState.Listening()
                startCapture()
            }
            VoiceSessionState.PROCESSING -> _uiState.value = VoiceUiState.Processing
            VoiceSessionState.SPEAKING -> _uiState.value = VoiceUiState.Speaking
            VoiceSessionState.RECONNECTING -> _uiState.value = VoiceUiState.Reconnecting(1)
            VoiceSessionState.ENDED -> _uiState.value = VoiceUiState.Idle
            VoiceSessionState.FAILED -> _uiState.value =
                VoiceUiState.Failed(VoiceErrorCode.INTERNAL_ERROR)
            VoiceSessionState.CONNECTING -> _uiState.value = VoiceUiState.Connecting
            VoiceSessionState.INTERRUPTING -> _uiState.value = VoiceUiState.Interrupting
            VoiceSessionState.IDLE -> _uiState.value = VoiceUiState.Idle
        }
    }

    private fun startCapture() {
        if (_muted.value || audioInput.active || ending) return
        when (audioInput.start(
            onSpeechDetected = {
                scope.launch {
                    if (machine.state == VoiceSessionState.SPEAKING) interruptAssistant()
                }
            },
            onFrame =(::enqueueAudioFrame),
            onFailure = { fail(VoiceErrorCode.AUDIO_INPUT_FAILURE) },
        )) {
            AndroidAudioInput.StartResult.STARTED -> Unit
            AndroidAudioInput.StartResult.PERMISSION_DENIED ->
                fail(VoiceErrorCode.MIC_PERMISSION_DENIED)
            AndroidAudioInput.StartResult.DEVICE_UNAVAILABLE ->
                fail(VoiceErrorCode.AUDIO_DEVICE_UNAVAILABLE)
        }
    }

    private fun enqueueAudioFrame(bytes: ByteArray) {
        synchronized(captureLock) {
            if (machine.state != VoiceSessionState.LISTENING || ending || _muted.value) return
            val frame = VoiceAudioFrame(currentTurnId, audioSequence++, bytes)
            if (!audioFrames.trySend(frame).isSuccess) {
                fail(VoiceErrorCode.AUDIO_INPUT_FAILURE)
            }
        }
    }

    private fun beginNewTurn() = synchronized(captureLock) {
        currentTurnId = newTurnId()
        audioSequence = 0
        drainAudioFrames()
    }

    private fun drainAudioFrames() {
        while (audioFrames.tryReceive().isSuccess) Unit
    }

    private fun fail(error: VoiceErrorCode) {
        if (ending) return
        ending = true
        if (machine.state !in setOf(VoiceSessionState.ENDED, VoiceSessionState.FAILED)) {
            runCatching { machine.transition(VoiceSessionState.FAILED) }
        }
        _uiState.value = VoiceUiState.Failed(error)
        audioInput.stop()
        audioOutput.stopImmediate()
        cleanupJob = scope.launch {
            val activeSession = session
            stopLocalResources()
            if (activeSession != null) backend.endVoiceSession(activeSession.id)
            session = null
            cleanupJob = null
        }
    }

    private suspend fun stopLocalResources() {
        audioInput.stop()
        audioOutput.stopImmediate()
        senderJob?.cancelAndJoin()
        senderJob = null
        runCatching { transport?.close() }
        transport = null
        connectionJob?.cancelAndJoin()
        connectionJob = null
        drainAudioFrames()
    }

    private fun ApiResult.Failure.toVoiceError(): VoiceErrorCode = when (category) {
        com.personalassistant.shared.ErrorCategory.AUTHENTICATION,
        com.personalassistant.shared.ErrorCategory.AUTHORIZATION,
        com.personalassistant.shared.ErrorCategory.DEVICE_REVOKED,
        -> VoiceErrorCode.VOICE_SESSION_AUTH_FAILED
        com.personalassistant.shared.ErrorCategory.NETWORK_UNAVAILABLE,
        com.personalassistant.shared.ErrorCategory.TIMEOUT,
        com.personalassistant.shared.ErrorCategory.SERVER_UNAVAILABLE,
        -> VoiceErrorCode.NETWORK_UNAVAILABLE
        else -> if (code == "REALTIME_MODEL_UNAVAILABLE") {
            VoiceErrorCode.REALTIME_MODEL_UNAVAILABLE
        } else {
            VoiceErrorCode.INTERNAL_ERROR
        }
    }

    companion object {
        fun newTurnId(): String = VoiceTurnIdentity.requireValid("android:${UUID.randomUUID()}")
    }
}
