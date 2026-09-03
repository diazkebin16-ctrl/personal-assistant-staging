package com.personalassistant.android.voice

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import com.personalassistant.shared.MaxBufferedVoiceFrames
import com.personalassistant.shared.VoiceSampleRateHz
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

class AndroidAudioOutput(
    context: Context,
    private val scope: CoroutineScope,
) {
    private val audioManager = context.getSystemService(AudioManager::class.java)
    private val chunks = Channel<AudioChunk>(MaxBufferedVoiceFrames)
    private var playbackJob: Job? = null
    private var track: AudioTrack? = null
    private var generation = 0L
    private var writtenFrames = 0L
    private var focusRequest: AudioFocusRequest? = null
    private var activeTurnId: String? = null
    private var expectedSequence = 0
    private var finalReceived = false

    val active: Boolean get() = playbackJob?.isActive == true

    @Synchronized
    fun offer(
        turnId: String,
        sequence: Int,
        bytes: ByteArray,
        final: Boolean,
        onComplete: (String) -> Unit,
        onFailure: () -> Unit,
        onFocusLost: () -> Unit,
    ): Boolean {
        if (finalReceived || sequence != expectedSequence) return false
        if (activeTurnId == null) {
            if (sequence != 0) return false
            activeTurnId = turnId
        } else if (activeTurnId != turnId) {
            return false
        }
        if (!ensurePlayback(onComplete, onFailure, onFocusLost)) return false
        val accepted = chunks.trySend(
            AudioChunk(generation, turnId, sequence, bytes, final),
        ).isSuccess
        if (accepted) {
            expectedSequence += 1
            finalReceived = final
        }
        return accepted
    }

    @Synchronized
    fun stopImmediate() {
        generation += 1
        while (chunks.tryReceive().isSuccess) Unit
        playbackJob?.cancel()
        playbackJob = null
        track?.let { output ->
            runCatching { output.pause() }
            runCatching { output.flush() }
            output.release()
        }
        track = null
        writtenFrames = 0
        focusRequest?.let(audioManager::abandonAudioFocusRequest)
        focusRequest = null
        audioManager.mode = AudioManager.MODE_NORMAL
        activeTurnId = null
        expectedSequence = 0
        finalReceived = false
    }

    fun supportedRouteTypes(): Set<Int> = if (android.os.Build.VERSION.SDK_INT >= 31) {
        audioManager.availableCommunicationDevices.map { it.type }.toSet()
    } else {
        emptySet()
    }

    private fun ensurePlayback(
        onComplete: (String) -> Unit,
        onFailure: () -> Unit,
        onFocusLost: () -> Unit,
    ): Boolean {
        if (active) return true
        val attributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .build()
        val focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
            .setAudioAttributes(attributes)
            .setOnAudioFocusChangeListener { change ->
                if (change in setOf(
                        AudioManager.AUDIOFOCUS_LOSS,
                        AudioManager.AUDIOFOCUS_LOSS_TRANSIENT,
                        AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK,
                    )
                ) {
                    stopImmediate()
                    onFocusLost()
                }
            }
            .build()
        if (audioManager.requestAudioFocus(focus) != AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
            onFailure()
            return false
        }
        focusRequest = focus
        audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
        val minimum = AudioTrack.getMinBufferSize(
            VoiceSampleRateHz,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        if (minimum <= 0) {
            audioManager.abandonAudioFocusRequest(focus)
            focusRequest = null
            audioManager.mode = AudioManager.MODE_NORMAL
            onFailure()
            return false
        }
        val output = runCatching {
            AudioTrack.Builder()
                .setAudioAttributes(attributes)
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(VoiceSampleRateHz)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build(),
                )
                .setTransferMode(AudioTrack.MODE_STREAM)
                .setBufferSizeInBytes(maxOf(minimum, 7_680))
                .build()
        }.getOrNull()
        if (output == null) {
            audioManager.abandonAudioFocusRequest(focus)
            focusRequest = null
            audioManager.mode = AudioManager.MODE_NORMAL
            onFailure()
            return false
        }
        track = output
        writtenFrames = 0
        val activeGeneration = generation
        output.play()
        playbackJob = scope.launch(Dispatchers.IO) {
            while (isActive) {
                val chunk = chunks.receive()
                if (chunk.generation != activeGeneration) continue
                val written = output.write(chunk.bytes, 0, chunk.bytes.size, AudioTrack.WRITE_BLOCKING)
                if (written != chunk.bytes.size) {
                    onFailure()
                    break
                }
                writtenFrames += written / 2
                if (chunk.final) {
                    val completed = withTimeoutOrNull(5_000) {
                        while (output.playbackHeadPosition.toLong() < writtenFrames) delay(10)
                        true
                    } ?: false
                    if (completed && generation == activeGeneration) {
                        completeTurn(chunk.turnId)
                        onComplete(chunk.turnId)
                    }
                }
            }
        }
        return true
    }

    @Synchronized
    private fun completeTurn(turnId: String) {
        if (activeTurnId != turnId) return
        activeTurnId = null
        expectedSequence = 0
        finalReceived = false
    }

    private data class AudioChunk(
        val generation: Long,
        val turnId: String,
        val sequence: Int,
        val bytes: ByteArray,
        val final: Boolean,
    )
}
