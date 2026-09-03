package com.personalassistant.android

import com.personalassistant.android.data.ConversationRepository
import com.personalassistant.android.data.PayloadIntegrity
import com.personalassistant.android.work.DeliveryScheduler
import com.personalassistant.shared.ClientAuthorityBoundary
import com.personalassistant.shared.OfflineCachePolicy
import com.personalassistant.shared.OfflineOperationState
import com.personalassistant.shared.OfflineOperationStateMachine
import com.personalassistant.shared.OfflineRetryPolicy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OfflineArchitectureTest {
    @Test fun retryKeepsStableWorkIdentity() = assertEquals(
        DeliveryScheduler.uniqueWorkName("operation-1"),
        DeliveryScheduler.uniqueWorkName("operation-1"),
    )

    @Test fun newIntentGetsNewWorkIdentity() = assertNotEquals(
        DeliveryScheduler.uniqueWorkName("operation-1"),
        DeliveryScheduler.uniqueWorkName("operation-2"),
    )

    @Test fun workNameContainsOperationIdentity() = assertEquals(
        "message:operation-1",
        DeliveryScheduler.uniqueWorkName("operation-1"),
    )

    @Test fun fingerprintIsStable() = assertEquals(fingerprint(), fingerprint())
    @Test fun contentMutationChangesFingerprint() = assertNotEquals(fingerprint(), fingerprint(content = "changed"))
    @Test fun conversationMutationChangesFingerprint() = assertNotEquals(fingerprint(), fingerprint(conversationId = "conversation-2"))
    @Test fun idempotencyMutationChangesFingerprint() = assertNotEquals(fingerprint(), fingerprint(idempotencyKey = "android:operation-2"))
    @Test fun versionMutationChangesFingerprint() = assertNotEquals(fingerprint(), fingerprint(expectedVersion = 2))
    @Test fun operationTypeMutationChangesFingerprint() = assertNotEquals(fingerprint(), fingerprint(operationType = "UNKNOWN"))

    @Test fun repositoryAndSharedRetryBoundsAgree() = assertEquals(
        OfflineRetryPolicy.maxAttempts,
        ConversationRepository.MAX_ATTEMPTS,
    )

    @Test fun acknowledgedOperationIsTerminal() = assertTrue(OfflineOperationStateMachine.isTerminal(OfflineOperationState.ACKNOWLEDGED))
    @Test fun rejectedOperationIsTerminal() = assertTrue(OfflineOperationStateMachine.isTerminal(OfflineOperationState.REJECTED))
    @Test fun cancelledOperationIsTerminal() = assertTrue(OfflineOperationStateMachine.isTerminal(OfflineOperationState.CANCELLED))
    @Test fun pendingOperationIsNotTerminal() = assertFalse(OfflineOperationStateMachine.isTerminal(OfflineOperationState.PENDING))
    @Test fun financialExecutionRemainsImpossibleOffline() = assertFalse(ClientAuthorityBoundary.canExecuteExternalAction("buy"))
    @Test fun offlineQueueCannotMintAuthority() = assertFalse(ClientAuthorityBoundary.canCreateAuthorizedActionEnvelope())
    @Test fun activeQueueIsBounded() = assertEquals(100, OfflineCachePolicy.maxActiveOperations)

    private fun fingerprint(
        operationType: String = "TEXT_MESSAGE",
        conversationId: String = "conversation-1",
        idempotencyKey: String = "android:operation-1",
        expectedVersion: Int = 1,
        content: String = "hello",
    ) = PayloadIntegrity.fingerprint(
        operationType,
        conversationId,
        idempotencyKey,
        expectedVersion,
        content,
    )
}
