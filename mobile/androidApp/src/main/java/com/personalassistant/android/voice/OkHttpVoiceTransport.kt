package com.personalassistant.android.voice

import com.personalassistant.shared.VoiceClientEvent
import com.personalassistant.shared.VoiceServerEvent
import com.personalassistant.shared.VoiceTransport
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString

class OkHttpVoiceTransport(
    private val client: OkHttpClient,
    private val allowLocalCleartext: Boolean,
) : VoiceTransport {
    private val json = Json { ignoreUnknownKeys = false; explicitNulls = false }
    private val incoming = Channel<String>(capacity = MaxIncomingEvents)
    private val connected = AtomicBoolean(false)
    private var socket: WebSocket? = null

    override suspend fun connect(streamUrl: String, credential: String) {
        require(
            streamUrl.startsWith("wss://") ||
                (allowLocalCleartext && streamUrl.startsWith("ws://")),
        ) { "Voice transport requires WSS outside local emulator development" }
        require(credential.length in 32..256)
        check(socket == null)
        val request = Request.Builder()
            .url(streamUrl)
            .header("X-Voice-Session-Token", credential)
            .build()
        suspendCancellableCoroutine { continuation ->
            val listener = object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    if (connected.compareAndSet(false, true)) continuation.resume(Unit)
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    if (text.length > MaxIncomingEventCharacters || !incoming.trySend(text).isSuccess) {
                        webSocket.close(1009, "bounded voice buffer exceeded")
                        incoming.close(IllegalStateException("Voice input buffer exceeded"))
                    }
                }

                override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                    webSocket.close(1003, "binary protocol events are not accepted")
                    incoming.close(IllegalStateException("Unexpected binary voice event"))
                }

                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                    webSocket.close(code, null)
                    incoming.close()
                }

                override fun onFailure(webSocket: WebSocket, error: Throwable, response: Response?) {
                    if (connected.compareAndSet(false, true)) {
                        continuation.resumeWithException(IllegalStateException("Voice connection failed"))
                    }
                    incoming.close(IllegalStateException("Voice connection failed"))
                }
            }
            socket = client.newWebSocket(request, listener)
            continuation.invokeOnCancellation { socket?.cancel() }
        }
    }

    override suspend fun send(event: VoiceClientEvent) {
        val payload = json.encodeToString(VoiceClientEvent.serializer(), event)
        check(socket?.send(payload) == true) { "Voice transport is unavailable" }
    }

    override suspend fun receive(): VoiceServerEvent? {
        val payload = incoming.receiveCatching().getOrNull() ?: return null
        return json.decodeFromString(VoiceServerEvent.serializer(), payload)
    }

    override suspend fun close() {
        socket?.close(1000, "session closed")
        socket = null
        incoming.close()
    }

    companion object {
        const val MaxIncomingEvents = 64
        const val MaxIncomingEventCharacters = 128 * 1024
    }
}
