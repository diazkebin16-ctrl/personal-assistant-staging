package com.personalassistant.android.wake

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import androidx.core.content.ContextCompat
import com.personalassistant.shared.WakeConfidenceBucket
import com.personalassistant.shared.WakeWordConfig
import com.personalassistant.shared.WakeWordEngine
import com.personalassistant.shared.WakeWordEvent
import com.personalassistant.shared.WakeWordState
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class LocalWakeDetection(val confidenceBucket: WakeConfidenceBucket?)

/** Vendor/model implementations remain replaceable and never own Voice or authority. */
interface LocalWakeWordDetector {
    val available: Boolean
    val engineVersion: String
    val profileVersion: String
    fun processPcm16(samples: ShortArray, length: Int): LocalWakeDetection?
    fun reset()
    fun close()
}

/**
 * Safe release default until an approved, licensed local model is supplied.
 * It never opens the microphone and cannot fall back to cloud transcription.
 */
class UnavailableLocalWakeWordDetector : LocalWakeWordDetector {
    override val available = false
    override val engineVersion = "local-engine-v1"
    override val profileVersion = "untrained-v1"
    override fun processPcm16(samples: ShortArray, length: Int): LocalWakeDetection? = null
    override fun reset() = Unit
    override fun close() = Unit
}

class AndroidWakeWordEngine(
    private val context: Context,
    private val scope: CoroutineScope,
    private val detectorFactory: () -> LocalWakeWordDetector,
    private val registeredDeviceId: suspend () -> String?,
) : WakeWordEngine {
    private var detector = detectorFactory()
    private val _state = MutableStateFlow(WakeWordState.DISABLED)
    override val state: StateFlow<WakeWordState> = _state
    override val engineVersion: String get() = detector.engineVersion
    override val profileAvailable: Boolean get() = detector.available
    private var captureJob: Job? = null
    private var recorder: AudioRecord? = null
    private val detectionPending = AtomicBoolean(false)

    override suspend fun start(
        config: WakeWordConfig,
        onEvent: suspend (WakeWordEvent) -> Unit,
    ) {
        require(detector.available) { "Local wake profile is unavailable" }
        require(config.detectorProfileVersion == detector.profileVersion) {
            "Wake profile version mismatch"
        }
        require(
            ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED,
        ) { "Microphone permission is required" }
        stopCapture(closeDetector = false)
        val deviceId = requireNotNull(registeredDeviceId()) { "Registered device is required" }
        val minimum = AudioRecord.getMinBufferSize(
            SAMPLE_RATE_HZ,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        require(minimum > 0) { "Microphone is unavailable" }
        val localRecorder = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            SAMPLE_RATE_HZ,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            maxOf(minimum, FRAME_SAMPLES * 2 * 4),
        )
        require(localRecorder.state == AudioRecord.STATE_INITIALIZED) {
            localRecorder.release()
            "Microphone initialization failed"
        }
        recorder = localRecorder
        detector.reset()
        _state.value = WakeWordState.LISTENING
        captureJob = scope.launch(Dispatchers.IO) {
            val frame = ShortArray(FRAME_SAMPLES)
            try {
                localRecorder.startRecording()
                while (localRecorder.recordingState == AudioRecord.RECORDSTATE_RECORDING) {
                    val count = localRecorder.read(frame, 0, frame.size, AudioRecord.READ_BLOCKING)
                    if (count <= 0) error("Wake microphone read failed")
                    val detection = detector.processPcm16(frame, count) ?: continue
                    if (!detectionPending.compareAndSet(false, true)) continue
                    val event = WakeWordEvent(
                            eventId = "wake:${UUID.randomUUID()}",
                            deviceId = deviceId,
                            detectedAtEpochMillis = System.currentTimeMillis(),
                            engineVersion = detector.engineVersion,
                            detectorProfileVersion = detector.profileVersion,
                            confidenceBucket = detection.confidenceBucket,
                        )
                    _state.value = WakeWordState.DETECTED
                    scope.launch {
                        try {
                            onEvent(event)
                        } finally {
                            detectionPending.set(false)
                            if (captureJob?.isActive == true) {
                                _state.value = WakeWordState.LISTENING
                            }
                        }
                    }
                }
            } catch (_: Exception) {
                _state.value = WakeWordState.ERROR
            } finally {
                runCatching { localRecorder.stop() }
                localRecorder.release()
                if (recorder === localRecorder) recorder = null
            }
        }
    }

    override suspend fun stop() {
        stopCapture(closeDetector = true)
        detectionPending.set(false)
        _state.value = WakeWordState.DISABLED
    }

    override suspend fun suspendListening() {
        stopCapture(closeDetector = false)
        _state.value = WakeWordState.SUSPENDED
    }

    override suspend fun resume(
        config: WakeWordConfig,
        onEvent: suspend (WakeWordEvent) -> Unit,
    ) = start(config, onEvent)

    private suspend fun stopCapture(closeDetector: Boolean) {
        val job = captureJob
        captureJob = null
        recorder?.let { active ->
            runCatching { active.stop() }
        }
        if (job != null) job.cancelAndJoin()
        recorder?.release()
        recorder = null
        detector.reset()
        if (closeDetector) {
            detector.close()
            detector = detectorFactory()
        }
    }

    companion object {
        const val SAMPLE_RATE_HZ = 16_000
        const val FRAME_SAMPLES = 320
    }
}
