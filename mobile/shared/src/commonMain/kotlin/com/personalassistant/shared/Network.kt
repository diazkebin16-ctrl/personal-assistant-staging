package com.personalassistant.shared

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.plugins.HttpRequestTimeoutException
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.accept
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.get
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.isSuccess
import io.ktor.serialization.kotlinx.json.json
import io.ktor.serialization.JsonConvertException
import kotlinx.io.IOException
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json

sealed interface ApiResult<out T> {
    data class Success<T>(val value: T) : ApiResult<T>
    data class Failure(
        val category: ErrorCategory,
        val code: String? = null,
        val retryable: Boolean,
    ) : ApiResult<Nothing>
}

interface SessionHeadersProvider {
    suspend fun accessToken(): String?
    suspend fun registeredDeviceId(): String?
}

interface SafeNetworkTelemetry {
    fun completed(operation: String, requestId: String?, statusCode: Int, latencyMillis: Long)
    fun failed(operation: String, category: ErrorCategory)

    data object None : SafeNetworkTelemetry {
        override fun completed(operation: String, requestId: String?, statusCode: Int, latencyMillis: Long) = Unit
        override fun failed(operation: String, category: ErrorCategory) = Unit
    }
}

fun configuredHttpClient(engineClient: HttpClient): HttpClient = engineClient.config {
    install(ContentNegotiation) {
        json(Json { ignoreUnknownKeys = false; explicitNulls = false })
    }
    install(HttpTimeout) {
        connectTimeoutMillis = 10_000
        requestTimeoutMillis = 30_000
        socketTimeoutMillis = 30_000
    }
}

class BackendApiClient(
    baseUrl: String,
    private val client: HttpClient,
    private val session: SessionHeadersProvider,
    private val telemetry: SafeNetworkTelemetry = SafeNetworkTelemetry.None,
    private val allowLocalCleartext: Boolean = false,
) {
    private val baseUrl = baseUrl.trimEnd('/')

    init {
        require(baseUrl.startsWith("https://") || (allowLocalCleartext && baseUrl.startsWith("http://")))
    }

    suspend fun registerDevice(request: DeviceRegistrationRequest): ApiResult<DeviceResponse> =
        post("register_device", "/api/v1/devices/register", request, includeDevice = false)

    suspend fun me(): ApiResult<MeResponse> = get("me", "/api/v1/me")

    suspend fun meForRegisteredDevice(deviceId: String): ApiResult<MeResponse> =
        execute("me_registered_device") {
            client.get("$baseUrl/api/v1/me") {
                authenticated(includeDevice = false)
                header("X-Device-ID", deviceId)
            }
        }

    suspend fun health(): ApiResult<LivenessResponse> = getPublic("health", "/health/live")

    suspend fun createConversation(request: ConversationCreateRequest): ApiResult<ConversationResponse> =
        post("create_conversation", "/api/v1/conversations", request)

    suspend fun conversations(): ApiResult<List<ConversationResponse>> =
        get("list_conversations", "/api/v1/conversations")

    suspend fun messages(conversationId: String): ApiResult<List<ConversationMessageResponse>> =
        get("list_messages", "/api/v1/conversations/$conversationId/messages")

    suspend fun submitMessage(
        conversationId: String,
        request: AssistantRequest,
    ): ApiResult<AssistantResponse> = post(
        "submit_message",
        "/api/v1/conversations/$conversationId/messages",
        request.copy(idempotencyKey = IdempotencyIdentity.requireValid(request.idempotencyKey)),
    )

    suspend fun approveConfirmation(confirmationId: String): ApiResult<ConfirmationResponse> =
        execute("approve_confirmation") {
            client.post("$baseUrl/api/v1/confirmations/$confirmationId/approve") {
                authenticated(includeDevice = true)
            }
        }

    suspend fun startVoiceSession(
        request: VoiceSessionCreateRequest,
    ): ApiResult<VoiceSessionResponse> = post(
        "start_voice_session",
        "/api/v1/voice/sessions",
        request,
    )

    suspend fun refreshVoiceCredential(
        sessionId: String,
    ): ApiResult<VoiceSessionCredentialResponse> = postNoBody(
        "refresh_voice_credential",
        "/api/v1/voice/sessions/$sessionId/credential",
    )

    suspend fun endVoiceSession(sessionId: String): ApiResult<VoiceSessionStateResponse> = postNoBody(
        "end_voice_session",
        "/api/v1/voice/sessions/$sessionId/end",
    )

    fun voiceStreamUrl(streamPath: String): String {
        require(streamPath.startsWith("/api/v1/voice/") && !streamPath.contains(".."))
        return when {
            baseUrl.startsWith("https://") -> "wss://${baseUrl.removePrefix("https://")}$streamPath"
            allowLocalCleartext && baseUrl.startsWith("http://") ->
                "ws://${baseUrl.removePrefix("http://")}$streamPath"
            else -> error("Voice transport requires WSS outside local emulator development")
        }
    }

    private suspend inline fun <reified T> get(operation: String, path: String): ApiResult<T> =
        execute(operation) {
            client.get("$baseUrl$path") { authenticated(includeDevice = true) }
        }

    private suspend inline fun <reified T> getPublic(operation: String, path: String): ApiResult<T> =
        execute(operation) {
            client.get("$baseUrl$path") { accept(ContentType.Application.Json) }
        }

    private suspend inline fun <reified Request : Any, reified Response> post(
        operation: String,
        path: String,
        body: Request,
        includeDevice: Boolean = true,
    ): ApiResult<Response> = execute(operation) {
        client.post("$baseUrl$path") {
            authenticated(includeDevice)
            setBody(body)
        }
    }

    private suspend inline fun <reified Response> postNoBody(
        operation: String,
        path: String,
    ): ApiResult<Response> = execute(operation) {
        client.post("$baseUrl$path") { authenticated(includeDevice = true) }
    }

    private suspend fun io.ktor.client.request.HttpRequestBuilder.authenticated(includeDevice: Boolean) {
        val token = session.accessToken()
        if (token != null) header(HttpHeaders.Authorization, "Bearer $token")
        if (includeDevice) session.registeredDeviceId()?.let { header("X-Device-ID", it) }
        accept(ContentType.Application.Json)
        header(HttpHeaders.ContentType, ContentType.Application.Json)
    }

    private suspend inline fun <reified T> execute(
        operation: String,
        block: () -> io.ktor.client.statement.HttpResponse,
    ): ApiResult<T> {
        val started = kotlin.time.TimeSource.Monotonic.markNow()
        return try {
            val response = block()
            val requestId = response.headers["X-Request-ID"]
            telemetry.completed(operation, requestId, response.status.value, started.elapsedNow().inWholeMilliseconds)
            if (response.status.isSuccess()) {
                ApiResult.Success(response.body())
            } else {
                val envelope = runCatching { response.body<ApiErrorEnvelope>() }.getOrNull()
                ApiResult.Failure(
                    category = category(response.status.value, envelope?.error?.code),
                    code = envelope?.error?.code,
                    retryable = response.status.value in 500..599,
                )
            }
        } catch (_: HttpRequestTimeoutException) {
            telemetry.failed(operation, ErrorCategory.TIMEOUT)
            ApiResult.Failure(ErrorCategory.TIMEOUT, retryable = true)
        } catch (_: IOException) {
            telemetry.failed(operation, ErrorCategory.NETWORK_UNAVAILABLE)
            ApiResult.Failure(ErrorCategory.NETWORK_UNAVAILABLE, retryable = true)
        } catch (_: SerializationException) {
            telemetry.failed(operation, ErrorCategory.VALIDATION)
            ApiResult.Failure(ErrorCategory.VALIDATION, retryable = false)
        } catch (_: JsonConvertException) {
            telemetry.failed(operation, ErrorCategory.VALIDATION)
            ApiResult.Failure(ErrorCategory.VALIDATION, retryable = false)
        }
    }

    private fun category(status: Int, code: String?): ErrorCategory = when {
        status == 401 -> ErrorCategory.AUTHENTICATION
        code == "DEVICE_REVOKED" -> ErrorCategory.DEVICE_REVOKED
        code?.contains("CONFIRMATION") == true -> ErrorCategory.CONFIRMATION_REQUIRED
        code?.contains("PERMISSION") == true -> ErrorCategory.PERMISSION_REQUIRED
        code?.contains("SAFE_MODE") == true -> ErrorCategory.SAFE_MODE
        status == 403 -> ErrorCategory.AUTHORIZATION
        status == 409 -> ErrorCategory.CONFLICT
        status == 422 -> ErrorCategory.VALIDATION
        status >= 500 -> ErrorCategory.SERVER_UNAVAILABLE
        else -> ErrorCategory.INTERNAL
    }
}


class SupabaseAuthApi(
    supabaseUrl: String,
    private val anonKey: String,
    private val client: HttpClient,
) {
    private val baseUrl = supabaseUrl.trimEnd('/')

    init {
        require(baseUrl.startsWith("https://") || baseUrl.isEmpty())
    }

    suspend fun signIn(email: String, password: String): ApiResult<SupabaseSessionResponse> =
        token("password", PasswordGrantRequest(email, password))

    suspend fun refresh(refreshToken: String): ApiResult<SupabaseSessionResponse> =
        token("refresh_token", RefreshGrantRequest(refreshToken))

    private suspend inline fun <reified T : Any> token(grantType: String, request: T): ApiResult<SupabaseSessionResponse> {
        if (baseUrl.isEmpty() || anonKey.isEmpty()) {
            return ApiResult.Failure(ErrorCategory.INTERNAL, "AUTH_NOT_CONFIGURED", false)
        }
        return try {
            val response = client.post("$baseUrl/auth/v1/token") {
                parameter("grant_type", grantType)
                header("apikey", anonKey)
                accept(ContentType.Application.Json)
                header(HttpHeaders.ContentType, ContentType.Application.Json)
                setBody(request)
            }
            if (response.status.isSuccess()) ApiResult.Success(response.body())
            else ApiResult.Failure(ErrorCategory.AUTHENTICATION, "AUTH_REJECTED", false)
        } catch (_: HttpRequestTimeoutException) {
            ApiResult.Failure(ErrorCategory.TIMEOUT, retryable = true)
        } catch (_: IOException) {
            ApiResult.Failure(ErrorCategory.NETWORK_UNAVAILABLE, retryable = true)
        } catch (_: SerializationException) {
            ApiResult.Failure(ErrorCategory.VALIDATION, retryable = false)
        } catch (_: JsonConvertException) {
            ApiResult.Failure(ErrorCategory.VALIDATION, retryable = false)
        }
    }
}
