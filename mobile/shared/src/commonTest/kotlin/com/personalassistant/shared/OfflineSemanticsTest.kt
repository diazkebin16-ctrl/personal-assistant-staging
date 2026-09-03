package com.personalassistant.shared

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

class OfflineSemanticsTest {
    @Test fun connectivityDistinguishesOnline() = assertNotEquals(ConnectivityState.ONLINE, ConnectivityState.OFFLINE)
    @Test fun connectivityDistinguishesDegraded() = assertNotEquals(ConnectivityState.DEGRADED, ConnectivityState.OFFLINE)
    @Test fun connectivityDistinguishesRecovering() = assertNotEquals(ConnectivityState.RECOVERING, ConnectivityState.ONLINE)
    @Test fun connectivityDistinguishesUnknown() = assertNotEquals(ConnectivityState.UNKNOWN, ConnectivityState.DEGRADED)

    @Test fun pendingMayWaitForNetwork() = assertTransition(OfflineOperationState.PENDING, OfflineOperationState.WAITING_FOR_NETWORK)
    @Test fun pendingMayStartSync() = assertTransition(OfflineOperationState.PENDING, OfflineOperationState.SYNCING)
    @Test fun pendingMayCancelLocally() = assertTransition(OfflineOperationState.PENDING, OfflineOperationState.CANCELLED)
    @Test fun waitingMayStartSync() = assertTransition(OfflineOperationState.WAITING_FOR_NETWORK, OfflineOperationState.SYNCING)
    @Test fun retryableMayStartSync() = assertTransition(OfflineOperationState.RETRYABLE_FAILURE, OfflineOperationState.SYNCING)
    @Test fun authRequiredMayResume() = assertTransition(OfflineOperationState.AUTH_REQUIRED, OfflineOperationState.PENDING)
    @Test fun syncingMayAcknowledge() = assertTransition(OfflineOperationState.SYNCING, OfflineOperationState.ACKNOWLEDGED)
    @Test fun syncingMayFailRetryably() = assertTransition(OfflineOperationState.SYNCING, OfflineOperationState.RETRYABLE_FAILURE)
    @Test fun syncingMayRequireAuthentication() = assertTransition(OfflineOperationState.SYNCING, OfflineOperationState.AUTH_REQUIRED)
    @Test fun syncingMayBeRejected() = assertTransition(OfflineOperationState.SYNCING, OfflineOperationState.REJECTED)
    @Test fun syncingMayRecordCancellationRequest() = assertTransition(OfflineOperationState.SYNCING, OfflineOperationState.CANCEL_REQUESTED)
    @Test fun lateAckWinsOverCancellationRequest() = assertTransition(OfflineOperationState.CANCEL_REQUESTED, OfflineOperationState.ACKNOWLEDGED)
    @Test fun confirmedNoSendMayFinishCancellation() = assertTransition(OfflineOperationState.CANCEL_REQUESTED, OfflineOperationState.CANCELLED)

    @Test fun acknowledgedCannotReplay() = assertNoTransition(OfflineOperationState.ACKNOWLEDGED, OfflineOperationState.SYNCING)
    @Test fun cancelledCannotReplay() = assertNoTransition(OfflineOperationState.CANCELLED, OfflineOperationState.SYNCING)
    @Test fun rejectedCannotReplay() = assertNoTransition(OfflineOperationState.REJECTED, OfflineOperationState.SYNCING)
    @Test fun terminalFailureCannotReplay() = assertNoTransition(OfflineOperationState.TERMINAL_FAILURE, OfflineOperationState.SYNCING)
    @Test fun pendingCannotInventAcknowledgement() = assertNoTransition(OfflineOperationState.PENDING, OfflineOperationState.ACKNOWLEDGED)
    @Test fun waitingCannotInventAcknowledgement() = assertNoTransition(OfflineOperationState.WAITING_FOR_NETWORK, OfflineOperationState.ACKNOWLEDGED)
    @Test fun retryableCannotInventAcknowledgement() = assertNoTransition(OfflineOperationState.RETRYABLE_FAILURE, OfflineOperationState.ACKNOWLEDGED)
    @Test fun illegalTransitionFailsClosed() {
        assertFailsWith<IllegalArgumentException> {
            OfflineOperationStateMachine.requireTransition(OfflineOperationState.CANCELLED, OfflineOperationState.PENDING)
        }
    }

    @Test fun pendingIsAutomaticSyncEligible() = assertTrue(OfflineOperationStateMachine.isAutomaticSyncEligible(OfflineOperationState.PENDING))
    @Test fun waitingIsAutomaticSyncEligible() = assertTrue(OfflineOperationStateMachine.isAutomaticSyncEligible(OfflineOperationState.WAITING_FOR_NETWORK))
    @Test fun retryableIsAutomaticSyncEligible() = assertTrue(OfflineOperationStateMachine.isAutomaticSyncEligible(OfflineOperationState.RETRYABLE_FAILURE))
    @Test fun authRequiredIsNotAutomaticSyncEligible() = assertFalse(OfflineOperationStateMachine.isAutomaticSyncEligible(OfflineOperationState.AUTH_REQUIRED))
    @Test fun cancellationRequestIsNotAutomaticSyncEligible() = assertFalse(OfflineOperationStateMachine.isAutomaticSyncEligible(OfflineOperationState.CANCEL_REQUESTED))

    @Test fun networkFailureIsRetryableOnlyWhenTransportSaysSo() = assertEquals(
        OfflineFailureDisposition.RETRYABLE,
        classify(ErrorCategory.NETWORK_UNAVAILABLE, retryable = true),
    )
    @Test fun timeoutIsRetryable() = assertEquals(OfflineFailureDisposition.RETRYABLE, classify(ErrorCategory.TIMEOUT, retryable = true))
    @Test fun serverUnavailableIsRetryable() = assertEquals(OfflineFailureDisposition.RETRYABLE, classify(ErrorCategory.SERVER_UNAVAILABLE, retryable = true))
    @Test fun unmarkedNetworkFailureFailsClosed() = assertEquals(OfflineFailureDisposition.TERMINAL, classify(ErrorCategory.NETWORK_UNAVAILABLE))
    @Test fun authenticationWaitsForUser() = assertEquals(OfflineFailureDisposition.AUTH_REQUIRED, classify(ErrorCategory.AUTHENTICATION))
    @Test fun authorizationIsRejected() = assertEquals(OfflineFailureDisposition.REJECTED, classify(ErrorCategory.AUTHORIZATION))
    @Test fun permissionRevocationIsRejected() = assertEquals(OfflineFailureDisposition.REJECTED, classify(ErrorCategory.PERMISSION_REQUIRED))
    @Test fun confirmationExpirationIsRejected() = assertEquals(OfflineFailureDisposition.REJECTED, classify(ErrorCategory.CONFIRMATION_REQUIRED))
    @Test fun safeModeDenialIsRejected() = assertEquals(OfflineFailureDisposition.REJECTED, classify(ErrorCategory.SAFE_MODE))
    @Test fun idempotencyConflictIsNotRetried() = assertEquals(OfflineFailureDisposition.CONFLICT, classify(ErrorCategory.CONFLICT))
    @Test fun validationFailureIsTerminal() = assertEquals(OfflineFailureDisposition.TERMINAL, classify(ErrorCategory.VALIDATION))
    @Test fun deviceRevocationInvalidatesSession() = assertEquals(OfflineFailureDisposition.DEVICE_REVOKED, classify(ErrorCategory.DEVICE_REVOKED))
    @Test fun deviceRevocationCodeOverridesGenericCategory() = assertEquals(
        OfflineFailureDisposition.DEVICE_REVOKED,
        OfflineFailureClassifier.classify(OfflineFailure(ErrorCategory.AUTHORIZATION, "DEVICE_REVOKED")),
    )

    @Test fun firstRetryIsAllowed() = assertTrue(OfflineRetryPolicy.mayRetry(OfflineFailureDisposition.RETRYABLE, 1))
    @Test fun retryStopsAtBound() = assertFalse(OfflineRetryPolicy.mayRetry(OfflineFailureDisposition.RETRYABLE, OfflineRetryPolicy.maxAttempts))
    @Test fun authenticationNeverUsesAutomaticRetry() = assertFalse(OfflineRetryPolicy.mayRetry(OfflineFailureDisposition.AUTH_REQUIRED, 1))
    @Test fun rejectionNeverUsesAutomaticRetry() = assertFalse(OfflineRetryPolicy.mayRetry(OfflineFailureDisposition.REJECTED, 1))
    @Test fun conflictNeverUsesAutomaticRetry() = assertFalse(OfflineRetryPolicy.mayRetry(OfflineFailureDisposition.CONFLICT, 1))
    @Test fun backoffGrows() = assertTrue(OfflineRetryPolicy.backoffMillis(2, "operation-123") > OfflineRetryPolicy.backoffMillis(1, "operation-123"))
    @Test fun backoffIsStableForOperation() = assertEquals(OfflineRetryPolicy.backoffMillis(3, "operation-123"), OfflineRetryPolicy.backoffMillis(3, "operation-123"))
    @Test fun backoffIsBounded() = assertTrue(OfflineRetryPolicy.backoffMillis(100, "operation-123") <= OfflineRetryPolicy.maxDelayMillis)
    @Test fun invalidAttemptFailsClosed() {
        assertFailsWith<IllegalArgumentException> {
            OfflineRetryPolicy.backoffMillis(0, "operation-123")
        }
    }

    @Test fun criticalCacheIsNeverShownStale() = assertFalse(OfflineCachePolicy.staleDisplayAllowed(DataSensitivity.CRITICAL))
    @Test fun privateCacheMayBeShownWithStaleLabel() = assertTrue(OfflineCachePolicy.staleDisplayAllowed(DataSensitivity.PRIVATE))
    @Test fun queueHasFiniteBound() = assertTrue(OfflineCachePolicy.maxActiveOperations in 1..1_000)
    @Test fun messageCacheHasFiniteBound() = assertTrue(OfflineCachePolicy.maxMessagesPerConversation in 1..1_000)
    @Test fun terminalRetentionIsFinite() = assertTrue(OfflineCachePolicy.terminalRetentionMillis > 0)

    @Test fun localPendingPresentationIsNotAccepted() = assertEquals(PendingOperationPresentation.SAVED_LOCALLY, PendingOperationPresentationMapper.map(OfflineOperationState.PENDING))
    @Test fun syncingPresentationIsNotAccepted() = assertEquals(PendingOperationPresentation.SYNCHRONIZING, PendingOperationPresentationMapper.map(OfflineOperationState.SYNCING))
    @Test fun onlyAckPresentationIsAccepted() = assertEquals(PendingOperationPresentation.SERVER_ACCEPTED, PendingOperationPresentationMapper.map(OfflineOperationState.ACKNOWLEDGED))
    @Test fun rejectedPresentationIsExplicit() = assertEquals(PendingOperationPresentation.REJECTED, PendingOperationPresentationMapper.map(OfflineOperationState.REJECTED))
    @Test fun authPresentationRequiresAttention() = assertEquals(PendingOperationPresentation.REQUIRES_ATTENTION, PendingOperationPresentationMapper.map(OfflineOperationState.AUTH_REQUIRED))
    @Test fun cancellationRacePresentationRequiresAttention() = assertEquals(PendingOperationPresentation.REQUIRES_ATTENTION, PendingOperationPresentationMapper.map(OfflineOperationState.CANCEL_REQUESTED))

    private fun classify(category: ErrorCategory, retryable: Boolean = false) =
        OfflineFailureClassifier.classify(OfflineFailure(category, serverMarkedRetryable = retryable))

    private fun assertTransition(from: OfflineOperationState, to: OfflineOperationState) {
        assertTrue(OfflineOperationStateMachine.canTransition(from, to))
        OfflineOperationStateMachine.requireTransition(from, to)
    }

    private fun assertNoTransition(from: OfflineOperationState, to: OfflineOperationState) {
        assertFalse(OfflineOperationStateMachine.canTransition(from, to))
    }
}
