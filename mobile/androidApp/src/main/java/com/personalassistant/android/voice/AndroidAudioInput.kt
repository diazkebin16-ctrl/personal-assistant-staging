package com.personalassistant.android.voice

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import androidx.core.content.ContextCompat
import com.personalassistant.shared.VoiceChannels
import com.personalassistant.shared.VoiceFrameBytes
import com.personalassistant.shared.VoiceSampleRateHz
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlin.math.abs
import kotlin.math.max

class AndroidAudioInput(
    context: Context,
    private val scope: CoroutineScope,
) {
    enum class StartResult { STARTED, PERMISSION_DENIED, DEVICE_UNAVAILABLE }

    private val appContext = context.applicationContext
    private var recorder: AudioRecord? = null
    private var captureJob: Job? = null

    val active: Boolean get() = captureJob?.isActive == true

    fun start(
        onSpeechDetected: () -> Unit,
        onFrame: (ByteArray) -> Unit,
        onFailure: () -> Unit,
    ): StartResult {
        if (ContextCompat.checkSelfPermission(appContext, Manifest.permission.RECORD_AUDIO) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            return StartResult.PERMISSION_DENIED
        }
        if (active) return StartResult.STARTED
        val channel = if (VoiceChannels == 1) {
            AudioFormat.CHANNEL_IN_MONO
        } else {
            throw IllegalStateException("Only mono voice capture is certified")
        }
        val minimum = AudioRecord.getMinBufferSize(
            VoiceSampleRateHz,
            channel,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        if (minimum <= 0) return StartResult.DEVICE_UNAVAILABLE
        val record = runCatching {
            AudioRecord.Builder()
                .setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(VoiceSampleRateHz)
                        .setChannelMask(channel)
                        .build(),
                )
                .setBufferSizeInBytes(max(minimum, VoiceFrameBytes * 8))
                .build()
        }.getOrNull() ?: return StartResult.DEVICE_UNAVAILABLE
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            record.release()
            return StartResult.DEVICE_UNAVAILABLE
        }
        if (runCatching { record.startRecording() }.isFailure) {
            record.release()
            return StartResult.DEVICE_UNAVAILABLE
        }
        recorder = record
        captureJob = scope.launch(Dispatchers.IO) {
            val buffer = ByteArray(VoiceFrameBytes)
            var speechLatched = false
            while (isActive && record.recordingState == AudioRecord.RECORDSTATE_RECORDING) {
                val read = record.read(buffer, 0, buffer.size, AudioRecord.READ_BLOCKING)
                if (read <= 0 || read % 2 != 0) {
                    onFailure()
                    break
                }
                val frame = buffer.copyOf(read)
                val speech = containsSpeech(frame)
                if (speech && !speechLatched) onSpeechDetected()
                speechLatched = speech
                onFrame(frame)
            }
        }
        return StartResult.STARTED
    }

    fun stop() {
        captureJob?.cancel()
        captureJob = null
        recorder?.let { activeRecorder ->
            runCatching { activeRecorder.stop() }
            activeRecorder.release()
        }
        recorder = null
    }

    private fun containsSpeech(frame: ByteArray): Boolean {
        var peak = 0
        var index = 0
        while (index + 1 < frame.size) {
            val sample = ((frame[index + 1].toInt() shl 8) or (frame[index].toInt() and 0xff))
                .toShort()
                .toInt()
            peak = max(peak, abs(sample))
            index += 2
        }
        return peak >= SpeechAmplitudeThreshold
    }

    companion object {
        const val SpeechAmplitudeThreshold = 2_500
    }
}
