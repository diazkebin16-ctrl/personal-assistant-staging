package com.personalassistant.shared

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.HttpMethod
import io.ktor.http.headersOf
import io.ktor.http.content.OutgoingContent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.descriptors.elementNames
import kotlinx.serialization.ExperimentalSerializationApi
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

class BackendApiClientTest {
    private val session = object : SessionHeadersProvider {
        override suspend fun accessToken() = "access-token-secret"
        override suspend fun registeredDeviceId() = "7b845df6-d48b-4bab-9c25-bbe707ac57a7"
    }

    @Test fun authenticatedConversationCallCarriesBearerAndDevice() = runTest {
        var captured: HttpRequestData? = null
        val api = api { request ->
            captured = request
            respond("[]", headers = jsonHeaders())
        }
        assertIs<ApiResult.Success<List<ConversationResponse>>>(api.conversations())
        assertEquals("Bearer access-token-secret", captured?.headers?.get(HttpHeaders.Authorization))
        assertEquals(session.registeredDeviceId(), captured?.headers?.get("X-Device-ID"))
    }

    @Test fun authenticatedAndroidDeviceConversationFlowIsTruthfulEndToEnd() = runTest {
        val authClient = configuredHttpClient(HttpClient(MockEngine { request ->
            assertEquals("/auth/v1/token", request.url.encodedPath)
            respond(authJson, headers = jsonHeaders())
        }))
        val authResult = SupabaseAuthApi("https://identity.example", "public-anon-key", authClient)
            .signIn("owner@example.test", "not-a-production-credential")
        val authenticated = assertIs<ApiResult.Success<SupabaseSessionResponse>>(authResult).value

        var registeredDeviceId: String? = null
        val authenticatedSession = object : SessionHeadersProvider {
            override suspend fun accessToken() = authenticated.accessToken
            override suspend fun registeredDeviceId() = registeredDeviceId
        }
        val calls = mutableListOf<String>()
        val backendHttp = configuredHttpClient(HttpClient(MockEngine { request ->
            calls += "${request.method.value} ${request.url.encodedPath}"
            assertEquals("Bearer ${authenticated.accessToken}", request.headers[HttpHeaders.Authorization])
            when {
                request.url.encodedPath.endsWith("/devices/register") -> {
                    assertNull(request.headers["X-Device-ID"])
                    respond(deviceJson, headers = jsonHeaders())
                }
                request.method == HttpMethod.Post && request.url.encodedPath.endsWith("/conversations") ->
                    respond(conversationJson, headers = jsonHeaders())
                request.method == HttpMethod.Post && request.url.encodedPath.endsWith("/messages") ->
                    respond(assistantJson, headers = jsonHeaders())
                else -> respond(messagesJson, headers = jsonHeaders())
            }
        }))
        val backend = BackendApiClient("https://backend.example", backendHttp, authenticatedSession)

        val device = assertIs<ApiResult.Success<DeviceResponse>>(
            backend.registerDevice(DeviceRegistrationRequest("Phone", platform = "android-35", deviceIdentifier = "android:abcdefgh", capabilities = emptyMap())),
        ).value
        registeredDeviceId = device.id
        val conversation = assertIs<ApiResult.Success<ConversationResponse>>(
            backend.createConversation(ConversationCreateRequest()),
        ).value
        val response = assertIs<ApiResult.Success<AssistantResponse>>(
            backend.submitMessage(conversation.id, AssistantRequest("hello", "android:logical-message-1", conversation.version)),
        ).value
        val history = assertIs<ApiResult.Success<List<ConversationMessageResponse>>>(
            backend.messages(conversation.id),
        ).value

        assertIs<TruthfulUiState.Answered>(TruthfulResponseMapper.map(response))
        assertEquals(listOf("POST /api/v1/devices/register", "POST /api/v1/conversations", "POST /api/v1/conversations/conversation/messages", "GET /api/v1/conversations/conversation/messages"), calls)
        assertEquals(2, history.size)
        assertEquals(response.assistantMessage.id, history.last().id)
    }

    @Test fun deviceRegistrationDoesNotClaimServerDeviceId() = runTest {
        var captured: HttpRequestData? = null
        val api = api { request ->
            captured = request
            respond(deviceJson, headers = jsonHeaders())
        }
        val request = DeviceRegistrationRequest("Phone", platform = "android-35", deviceIdentifier = "android:abcdefgh", capabilities = emptyMap())
        assertIs<ApiResult.Success<DeviceResponse>>(api.registerDevice(request))
        assertNull(captured?.headers?.get("X-Device-ID"))
    }

    @Test fun messageSubmissionPreservesIdempotencyInBody() = runTest {
        var body = ""
        val api = api { request ->
            body = (request.body as OutgoingContent.ByteArrayContent).bytes().decodeToString()
            respond(assistantJson, headers = jsonHeaders())
        }
        val result = api.submitMessage("conversation", AssistantRequest("hello", "android:12345678", 1))
        assertIs<ApiResult.Success<AssistantResponse>>(result)
        assertTrue(body.contains("android:12345678"))
    }

    @Test fun malformedResponseFailsClosed() = runTest {
        val result = api { respond("{not-json", headers = jsonHeaders()) }.conversations()
        assertIs<ApiResult.Failure>(result)
        assertEquals(ErrorCategory.VALIDATION, result.category)
        assertFalse(result.retryable)
    }

    @Test fun serverFailureIsRetryable() = runTest {
        val result = api { respondError(HttpStatusCode.ServiceUnavailable) }.conversations()
        assertIs<ApiResult.Failure>(result)
        assertEquals(ErrorCategory.SERVER_UNAVAILABLE, result.category)
        assertTrue(result.retryable)
    }

    @Test fun healthProbeIsPublicAndTyped() = runTest {
        var captured: HttpRequestData? = null
        val api = api { request ->
            captured = request
            respond("{\"status\":\"healthy\",\"service\":\"personal-assistant\"}", headers = jsonHeaders())
        }
        assertIs<ApiResult.Success<LivenessResponse>>(api.health())
        assertNull(captured?.headers?.get(HttpHeaders.Authorization))
        assertNull(captured?.headers?.get("X-Device-ID"))
    }

    @Test fun authenticationFailureIsNotRetryable() = runTest {
        val result = api { respondError(HttpStatusCode.Unauthorized) }.conversations()
        assertIs<ApiResult.Failure>(result)
        assertEquals(ErrorCategory.AUTHENTICATION, result.category)
        assertFalse(result.retryable)
    }

    @Test fun idempotencyConflictIsNotRetryable() = runTest {
        val error = "{\"error\":{\"code\":\"MESSAGE_IDEMPOTENCY_CONFLICT\",\"message\":\"conflict\"}}"
        val result = api { respond(error, HttpStatusCode.Conflict, jsonHeaders()) }.conversations()
        assertIs<ApiResult.Failure>(result)
        assertEquals(ErrorCategory.CONFLICT, result.category)
        assertFalse(result.retryable)
    }

    @Test fun expiredConfirmationIsClassifiedBeforeGenericConflict() = runTest {
        val error = "{\"error\":{\"code\":\"CONFIRMATION_EXPIRED\",\"message\":\"expired\"}}"
        val result = api { respond(error, HttpStatusCode.Conflict, jsonHeaders()) }.conversations()
        assertIs<ApiResult.Failure>(result)
        assertEquals(ErrorCategory.CONFIRMATION_REQUIRED, result.category)
        assertFalse(result.retryable)
    }

    @Test fun authorizationFailureIsNotRetryable() = runTest {
        val error = "{\"error\":{\"code\":\"DEVICE_REVOKED\",\"message\":\"revoked\"}}"
        val result = api { respond(error, HttpStatusCode.Forbidden, jsonHeaders()) }.conversations()
        assertIs<ApiResult.Failure>(result)
        assertEquals(ErrorCategory.DEVICE_REVOKED, result.category)
        assertFalse(result.retryable)
    }

    @Test fun confirmationUsesCertifiedServerEndpoint() = runTest {
        var path = ""
        val api = api { request ->
            path = request.url.encodedPath
            respond(confirmationJson, headers = jsonHeaders())
        }
        assertIs<ApiResult.Success<ConfirmationResponse>>(api.approveConfirmation("confirmation-id"))
        assertEquals("/api/v1/confirmations/confirmation-id/approve", path)
    }

    @OptIn(ExperimentalSerializationApi::class)
    @Test fun clientSurfaceHasNoProviderOrModelOverride() {
        val properties = AssistantRequest.serializer().descriptor.elementNames.toSet()
        assertFalse("model" in properties)
        assertFalse("provider" in properties)
        assertFalse("user_id" in properties)
        assertFalse("authorized_action_envelope" in properties)
    }

    private fun api(handler: suspend MockRequestHandleScope.(HttpRequestData) -> HttpResponseData): BackendApiClient {
        val client = configuredHttpClient(HttpClient(MockEngine(handler)))
        return BackendApiClient("https://backend.example", client, session)
    }

    private fun jsonHeaders() = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString())

    private val deviceJson = """{"id":"d","device_name":"Phone","device_type":"ANDROID","platform":"android-35","trusted":false,"capabilities":{},"has_public_key":true,"created_at":"t","updated_at":"t","last_seen_at":"t","revoked_at":null}"""
    private val authJson = """{"access_token":"test-jwt","refresh_token":"test-refresh","expires_in":3600,"token_type":"bearer"}"""
    private val conversationJson = """{"id":"conversation","device_id":"d","title":null,"version":1,"created_at":"t","updated_at":"t","last_message_at":null}"""
    private val confirmationJson = """{"id":"confirmation-id","authorization_decision_id":"a","capability_key":"memory","action":"delete","status":"APPROVED","requested_at":"t","expires_at":"t","confirmed_at":"t"}"""
    private val assistantJson = """{"conversation":{"id":"conversation","device_id":null,"title":null,"version":2,"created_at":"t","updated_at":"t","last_message_at":"t"},"user_message":{"id":"u","conversation_id":"conversation","role":"USER","status":"COMPLETED","outcome":null,"sequence":1,"content":"hello","sensitivity":"PUBLIC","created_at":"t"},"assistant_message":{"id":"a","conversation_id":"conversation","role":"ASSISTANT","status":"COMPLETED","outcome":"ANSWERED","sequence":2,"content":"hi","sensitivity":"PUBLIC","created_at":"t"}}"""
    private val messagesJson = """[{"id":"u","conversation_id":"conversation","role":"USER","status":"COMPLETED","outcome":null,"sequence":1,"content":"hello","sensitivity":"PUBLIC","created_at":"t"},{"id":"a","conversation_id":"conversation","role":"ASSISTANT","status":"COMPLETED","outcome":"ANSWERED","sequence":2,"content":"hi","sensitivity":"PUBLIC","created_at":"t"}]"""
}
