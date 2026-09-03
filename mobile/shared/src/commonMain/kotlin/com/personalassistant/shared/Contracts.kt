package com.personalassistant.shared

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
enum class DeviceType { ANDROID }

@Serializable
enum class MessageRole { USER, ASSISTANT }

@Serializable
enum class MessageStatus { COMPLETED, FAILED }

@Serializable
enum class AssistantOutcome {
    ANSWERED,
    MEMORY_SAVED,
    MEMORY_RECALLED,
    MEMORY_PERMISSION_REQUIRED,
    MEMORY_TARGET_REQUIRED,
    MEMORY_CONFIRMATION_REQUIRED,
    MEMORY_DELETED,
    ACTION_WAITING_PERMISSION,
    ACTION_WAITING_CONFIRMATION,
    ACTION_READY_FOR_FUTURE_EXECUTION,
    ACTION_DENIED,
    ACTION_UNSUPPORTED,
    RESEARCH_ANSWERED,
    RESEARCH_PERMISSION_REQUIRED,
    RESEARCH_CONFIRMATION_REQUIRED,
    RESEARCH_POLICY_DENIED,
    RESEARCH_UNAVAILABLE,
    RESEARCH_INSUFFICIENT_EVIDENCE,
    FAILED,
}

@Serializable
enum class DataSensitivity { PUBLIC, INTERNAL, PRIVATE, SENSITIVE, CRITICAL }

@Serializable
data class DeviceRegistrationRequest(
    @SerialName("device_name") val deviceName: String,
    @SerialName("device_type") val deviceType: DeviceType = DeviceType.ANDROID,
    val platform: String,
    @SerialName("device_identifier") val deviceIdentifier: String,
    val capabilities: Map<String, Boolean>,
    @SerialName("public_key") val publicKey: String? = null,
)

@Serializable
data class DeviceResponse(
    val id: String,
    @SerialName("device_name") val deviceName: String,
    @SerialName("device_type") val deviceType: DeviceType,
    val platform: String,
    val trusted: Boolean,
    val capabilities: Map<String, Boolean>,
    @SerialName("has_public_key") val hasPublicKey: Boolean,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
    @SerialName("last_seen_at") val lastSeenAt: String,
    @SerialName("revoked_at") val revokedAt: String? = null,
)

@Serializable
data class MeResponse(
    @SerialName("user_id") val userId: String,
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("device_id") val deviceId: String? = null,
    val authenticated: Boolean,
    @SerialName("authentication_level") val authenticationLevel: String,
)

@Serializable
data class ConversationCreateRequest(val title: String? = null)

@Serializable
data class ConversationResponse(
    val id: String,
    @SerialName("device_id") val deviceId: String? = null,
    val title: String? = null,
    val version: Int,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
    @SerialName("last_message_at") val lastMessageAt: String? = null,
)

@Serializable
data class AssistantRequest(
    val content: String,
    @SerialName("idempotency_key") val idempotencyKey: String,
    @SerialName("expected_version") val expectedVersion: Int,
    @SerialName("use_memory_context") val useMemoryContext: Boolean = true,
    @SerialName("memory_items_per_category") val memoryItemsPerCategory: Int = 3,
    @SerialName("requested_output_tokens") val requestedOutputTokens: Int = 1024,
    @SerialName("research_confirmation_id") val researchConfirmationId: String? = null,
)

@Serializable
data class ResearchCitationResponse(
    @SerialName("citation_id") val citationId: String,
    @SerialName("evidence_id") val evidenceId: String,
    val url: String,
    val title: String,
    @SerialName("retrieved_at") val retrievedAt: String,
    val locator: String,
) {
    fun isSafeWebUrl(): Boolean {
        val normalized = url.lowercase()
        val schemeLength = when {
            normalized.startsWith("https://") -> 8
            normalized.startsWith("http://") -> 7
            else -> return false
        }
        val authority = normalized.drop(schemeLength).substringBefore('/').substringBefore('?')
        if (authority.isEmpty() || '@' in authority) return false
        val host = if (authority.startsWith("[")) {
            authority.substringAfter('[').substringBefore(']')
        } else {
            authority.substringBefore(':').trimEnd('.')
        }
        return host != "localhost" && !host.endsWith(".localhost") &&
            !host.endsWith(".local") && !host.endsWith(".internal") &&
            !host.startsWith("127.") && !host.startsWith("10.") &&
            !host.startsWith("192.168.") && !host.startsWith("169.254.") &&
            !Regex("^172\\.(1[6-9]|2[0-9]|3[01])\\.").containsMatchIn(host) &&
            host != "::1" && !(":" in host && (
                host.startsWith("fc") || host.startsWith("fd") ||
                    Regex("^fe[89ab]").containsMatchIn(host)
                ))
    }
}

@Serializable
data class ConversationMessageResponse(
    val id: String,
    @SerialName("conversation_id") val conversationId: String,
    val role: MessageRole,
    val status: MessageStatus,
    val outcome: AssistantOutcome? = null,
    val sequence: Int,
    val content: String,
    val sensitivity: DataSensitivity,
    @SerialName("orchestration_id") val orchestrationId: String? = null,
    @SerialName("confirmation_request_id") val confirmationRequestId: String? = null,
    @SerialName("memory_id") val memoryId: String? = null,
    @SerialName("reason_code") val reasonCode: String? = null,
    val citations: List<ResearchCitationResponse> = emptyList(),
    @SerialName("created_at") val createdAt: String,
)

@Serializable
data class AssistantResponse(
    val conversation: ConversationResponse,
    @SerialName("user_message") val userMessage: ConversationMessageResponse,
    @SerialName("assistant_message") val assistantMessage: ConversationMessageResponse,
)

@Serializable
data class ApiErrorDetail(val code: String, val message: String)

@Serializable
data class ApiErrorEnvelope(val error: ApiErrorDetail)

@Serializable
data class LivenessResponse(val status: String, val service: String)

@Serializable
data class ConfirmationResponse(
    val id: String,
    @SerialName("authorization_decision_id") val authorizationDecisionId: String,
    @SerialName("capability_key") val capabilityKey: String,
    val action: String,
    val status: String,
    @SerialName("requested_at") val requestedAt: String,
    @SerialName("expires_at") val expiresAt: String,
    @SerialName("confirmed_at") val confirmedAt: String? = null,
    @SerialName("rejected_at") val rejectedAt: String? = null,
    @SerialName("consumed_at") val consumedAt: String? = null,
)

@Serializable
data class SupabaseSessionResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("expires_in") val expiresIn: Long,
    @SerialName("token_type") val tokenType: String,
)

@Serializable
data class PasswordGrantRequest(val email: String, val password: String)

@Serializable
data class RefreshGrantRequest(@SerialName("refresh_token") val refreshToken: String)
