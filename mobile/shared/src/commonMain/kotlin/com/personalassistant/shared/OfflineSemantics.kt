package com.personalassistant.shared

/** Durable transport state. None of these values grants server authority. */
enum class OfflineOperationState {
    PENDING,
    WAITING_FOR_NETWORK,
    SYNCING,
    ACKNOWLEDGED,
    RETRYABLE_FAILURE,
    AUTH_REQUIRED,
    REJECTED,
    CANCEL_REQUESTED,
    CANCELLED,
    TERMINAL_FAILURE,
}

enum class OfflineFailureDisposition {
    RETRYABLE,
    AUTH_REQUIRED,
    REJECTED,
    CONFLICT,
    DEVICE_REVOKED,
    TERMINAL,
}

data class OfflineFailure(
    val category: ErrorCategory,
    val code: String? = null,
    val serverMarkedRetryable: Boolean = false,
)

object OfflineFailureClassifier {
    fun classify(failure: OfflineFailure): OfflineFailureDisposition = when {
        failure.code == "DEVICE_REVOKED" || failure.category == ErrorCategory.DEVICE_REVOKED ->
            OfflineFailureDisposition.DEVICE_REVOKED
        failure.category == ErrorCategory.AUTHENTICATION -> OfflineFailureDisposition.AUTH_REQUIRED
        failure.category == ErrorCategory.CONFLICT -> OfflineFailureDisposition.CONFLICT
        failure.category in setOf(
            ErrorCategory.AUTHORIZATION,
            ErrorCategory.CONFIRMATION_REQUIRED,
            ErrorCategory.PERMISSION_REQUIRED,
            ErrorCategory.SAFE_MODE,
        ) -> OfflineFailureDisposition.REJECTED
        failure.category in setOf(
            ErrorCategory.NETWORK_UNAVAILABLE,
            ErrorCategory.TIMEOUT,
            ErrorCategory.SERVER_UNAVAILABLE,
        ) && failure.serverMarkedRetryable -> OfflineFailureDisposition.RETRYABLE
        else -> OfflineFailureDisposition.TERMINAL
    }
}

/** Explicit fail-closed state transitions for locally persisted transport intent. */
object OfflineOperationStateMachine {
    private val transitions = mapOf(
        OfflineOperationState.PENDING to setOf(
            OfflineOperationState.WAITING_FOR_NETWORK,
            OfflineOperationState.SYNCING,
            OfflineOperationState.AUTH_REQUIRED,
            OfflineOperationState.REJECTED,
            OfflineOperationState.CANCELLED,
            OfflineOperationState.TERMINAL_FAILURE,
        ),
        OfflineOperationState.WAITING_FOR_NETWORK to setOf(
            OfflineOperationState.SYNCING,
            OfflineOperationState.AUTH_REQUIRED,
            OfflineOperationState.REJECTED,
            OfflineOperationState.CANCELLED,
            OfflineOperationState.TERMINAL_FAILURE,
        ),
        OfflineOperationState.RETRYABLE_FAILURE to setOf(
            OfflineOperationState.WAITING_FOR_NETWORK,
            OfflineOperationState.SYNCING,
            OfflineOperationState.AUTH_REQUIRED,
            OfflineOperationState.REJECTED,
            OfflineOperationState.CANCELLED,
            OfflineOperationState.TERMINAL_FAILURE,
        ),
        OfflineOperationState.AUTH_REQUIRED to setOf(
            OfflineOperationState.PENDING,
            OfflineOperationState.SYNCING,
            OfflineOperationState.REJECTED,
            OfflineOperationState.CANCELLED,
            OfflineOperationState.TERMINAL_FAILURE,
        ),
        OfflineOperationState.SYNCING to setOf(
            OfflineOperationState.ACKNOWLEDGED,
            OfflineOperationState.RETRYABLE_FAILURE,
            OfflineOperationState.AUTH_REQUIRED,
            OfflineOperationState.REJECTED,
            OfflineOperationState.CANCEL_REQUESTED,
            OfflineOperationState.TERMINAL_FAILURE,
        ),
        OfflineOperationState.CANCEL_REQUESTED to setOf(
            OfflineOperationState.ACKNOWLEDGED,
            OfflineOperationState.CANCELLED,
        ),
        OfflineOperationState.ACKNOWLEDGED to emptySet(),
        OfflineOperationState.REJECTED to emptySet(),
        OfflineOperationState.CANCELLED to emptySet(),
        OfflineOperationState.TERMINAL_FAILURE to emptySet(),
    )

    fun canTransition(from: OfflineOperationState, to: OfflineOperationState): Boolean =
        to in transitions.getValue(from)

    fun requireTransition(from: OfflineOperationState, to: OfflineOperationState) {
        require(canTransition(from, to)) { "Illegal offline operation transition: $from -> $to" }
    }

    fun isTerminal(state: OfflineOperationState): Boolean = transitions.getValue(state).isEmpty()

    fun isAutomaticSyncEligible(state: OfflineOperationState): Boolean = state in setOf(
        OfflineOperationState.PENDING,
        OfflineOperationState.WAITING_FOR_NETWORK,
        OfflineOperationState.RETRYABLE_FAILURE,
    )
}

object OfflineRetryPolicy {
    const val maxAttempts = 5
    const val baseDelayMillis = 30_000L
    const val maxDelayMillis = 6L * 60L * 60L * 1_000L

    fun mayRetry(disposition: OfflineFailureDisposition, completedAttempts: Int): Boolean =
        disposition == OfflineFailureDisposition.RETRYABLE && completedAttempts < maxAttempts

    /** Stable per-operation jitter avoids synchronized reconnect storms without changing identity. */
    fun backoffMillis(completedAttempts: Int, operationId: String): Long {
        require(completedAttempts >= 1)
        val exponent = (completedAttempts - 1).coerceAtMost(16)
        val raw = (baseDelayMillis * (1L shl exponent)).coerceAtMost(maxDelayMillis)
        val stableBucket = operationId.fold(0) { value, char -> (value * 31 + char.code) and 0x7fffffff } % 41
        val jitterPercent = 80 + stableBucket // 80%..120%
        return (raw * jitterPercent / 100L).coerceAtMost(maxDelayMillis)
    }
}

object OfflineCachePolicy {
    const val maxActiveOperations = 100
    const val maxMessagesPerConversation = 200
    const val terminalRetentionMillis = 7L * 24L * 60L * 60L * 1_000L

    fun staleDisplayAllowed(sensitivity: DataSensitivity): Boolean =
        sensitivity != DataSensitivity.CRITICAL
}

enum class PendingOperationPresentation {
    SAVED_LOCALLY,
    WAITING_FOR_CONNECTION,
    SYNCHRONIZING,
    SERVER_ACCEPTED,
    FAILED,
    REJECTED,
    REQUIRES_ATTENTION,
    CANCELLED,
}

object PendingOperationPresentationMapper {
    fun map(state: OfflineOperationState): PendingOperationPresentation = when (state) {
        OfflineOperationState.PENDING -> PendingOperationPresentation.SAVED_LOCALLY
        OfflineOperationState.WAITING_FOR_NETWORK,
        OfflineOperationState.RETRYABLE_FAILURE,
        -> PendingOperationPresentation.WAITING_FOR_CONNECTION
        OfflineOperationState.SYNCING -> PendingOperationPresentation.SYNCHRONIZING
        OfflineOperationState.ACKNOWLEDGED -> PendingOperationPresentation.SERVER_ACCEPTED
        OfflineOperationState.REJECTED -> PendingOperationPresentation.REJECTED
        OfflineOperationState.AUTH_REQUIRED,
        OfflineOperationState.CANCEL_REQUESTED,
        -> PendingOperationPresentation.REQUIRES_ATTENTION
        OfflineOperationState.CANCELLED -> PendingOperationPresentation.CANCELLED
        OfflineOperationState.TERMINAL_FAILURE -> PendingOperationPresentation.FAILED
    }
}
