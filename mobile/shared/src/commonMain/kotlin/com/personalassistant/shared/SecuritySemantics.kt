package com.personalassistant.shared

enum class CapabilityName {
    NOTIFICATIONS,
    LOCATION,
    CALENDAR_READ,
    CALENDAR_WRITE,
    CONTACTS_READ,
    MICROPHONE,
    CAMERA,
    FILES,
    SHARE,
    CLIPBOARD,
    DEVICE_STATE,
}

data class CapabilityState(
    val name: CapabilityName,
    val deviceSupports: Boolean,
    val osPermissionGranted: Boolean,
    val assistantPermissionGranted: Boolean,
    val actionAuthorized: Boolean,
) {
    val usable: Boolean
        get() = deviceSupports && osPermissionGranted && assistantPermissionGranted && actionAuthorized
}

enum class ConnectivityState { ONLINE, OFFLINE, DEGRADED, RECOVERING, UNKNOWN }

enum class ErrorCategory {
    AUTHENTICATION,
    AUTHORIZATION,
    NETWORK_UNAVAILABLE,
    TIMEOUT,
    SERVER_UNAVAILABLE,
    VALIDATION,
    CONFIRMATION_REQUIRED,
    PERMISSION_REQUIRED,
    SAFE_MODE,
    CONFLICT,
    DEVICE_REVOKED,
    UNSUPPORTED,
    INTERNAL,
}

sealed interface TruthfulUiState {
    data object Idle : TruthfulUiState
    data class Sending(val operationId: String) : TruthfulUiState
    data class Answered(val message: String) : TruthfulUiState
    data class WaitingConfirmation(val message: String, val confirmationId: String?) : TruthfulUiState
    data class WaitingPermission(val message: String) : TruthfulUiState
    data class ReadyButExecutorUnavailable(val message: String) : TruthfulUiState
    data class Unsupported(val message: String) : TruthfulUiState
    data class Denied(val message: String) : TruthfulUiState
    data class Failed(val category: ErrorCategory, val retryable: Boolean) : TruthfulUiState
}

object TruthfulResponseMapper {
    fun map(response: AssistantResponse): TruthfulUiState {
        val message = response.assistantMessage
        if (message.status == MessageStatus.FAILED) {
            return TruthfulUiState.Failed(ErrorCategory.INTERNAL, retryable = false)
        }
        return when (message.outcome) {
            AssistantOutcome.ACTION_WAITING_CONFIRMATION,
            AssistantOutcome.MEMORY_CONFIRMATION_REQUIRED,
            AssistantOutcome.RESEARCH_CONFIRMATION_REQUIRED,
            -> TruthfulUiState.WaitingConfirmation(message.content, message.confirmationRequestId)

            AssistantOutcome.ACTION_WAITING_PERMISSION,
            AssistantOutcome.MEMORY_PERMISSION_REQUIRED,
            AssistantOutcome.RESEARCH_PERMISSION_REQUIRED,
            -> TruthfulUiState.WaitingPermission(message.content)

            AssistantOutcome.ACTION_READY_FOR_FUTURE_EXECUTION ->
                TruthfulUiState.ReadyButExecutorUnavailable(message.content)

            AssistantOutcome.ACTION_UNSUPPORTED -> TruthfulUiState.Unsupported(message.content)
            AssistantOutcome.ACTION_DENIED,
            AssistantOutcome.RESEARCH_POLICY_DENIED,
            -> TruthfulUiState.Denied(message.content)

            AssistantOutcome.RESEARCH_UNAVAILABLE,
            AssistantOutcome.RESEARCH_INSUFFICIENT_EVIDENCE,
            -> TruthfulUiState.Unsupported(message.content)
            AssistantOutcome.FAILED, null ->
                TruthfulUiState.Failed(ErrorCategory.INTERNAL, retryable = false)

            else -> TruthfulUiState.Answered(message.content)
        }
    }
}

object ClientAuthorityBoundary {
    val financiallyProhibitedActions = setOf(
        "buy", "sell", "transfer", "withdraw", "deposit", "place_order",
        "change_leverage", "increase_risk", "financial_execution",
    )

    fun canExecuteExternalAction(@Suppress("UNUSED_PARAMETER") action: String): Boolean = false
    fun canCreateAuthorizedActionEnvelope(): Boolean = false
    fun canMutateServerTask(): Boolean = false
    fun canMutateServerMemory(): Boolean = false
    fun modelTextGrantsAuthority(@Suppress("UNUSED_PARAMETER") text: String): Boolean = false
}

object IdempotencyIdentity {
    private val allowed = Regex("^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
    fun requireValid(value: String): String {
        require(allowed.matches(value)) { "Invalid idempotency identity" }
        return value
    }
}

object RetryPolicy {
    const val maxAttempts = 5

    fun mayRetry(isRead: Boolean, hasStableIdempotency: Boolean, attemptCount: Int): Boolean =
        attemptCount < maxAttempts && (isRead || hasStableIdempotency)
}

data class ServerSecuritySnapshot(
    val safeModeKnown: Boolean,
    val safeModeAllowsActions: Boolean,
    val permissionKnown: Boolean,
    val permissionGranted: Boolean,
) {
    val mayRequestPrivilegedAction: Boolean
        get() = safeModeKnown && safeModeAllowsActions && permissionKnown && permissionGranted
}
