package com.personalassistant.android.sync

import com.personalassistant.android.auth.SessionManager
import com.personalassistant.android.data.local.AssistantDatabase
import com.personalassistant.android.work.DeliveryScheduler
import com.personalassistant.shared.ConnectivityState
import com.personalassistant.shared.ErrorCategory
import com.personalassistant.shared.OfflineCachePolicy
import com.personalassistant.shared.OfflineOperationState
import com.personalassistant.shared.OfflineRetryPolicy
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** Event-driven recovery and scheduling. Workers remain the only network delivery authority. */
class OfflineSyncCoordinator(
    private val database: AssistantDatabase,
    private val scheduler: DeliveryScheduler,
    private val sessions: SessionManager,
    connectivity: StateFlow<ConnectivityState>,
    private val scope: CoroutineScope,
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val coordinationMutex = Mutex()

    init {
        scope.launch {
            recoverInterruptedWork()
            connectivity.collectLatest { state ->
                if (state == ConnectivityState.ONLINE) synchronizeEligible()
            }
        }
    }

    fun onAuthenticated() {
        scope.launch {
            val binding = sessions.currentAuthorityBinding() ?: return@launch
            database.pendingOperations().resumeAfterAuthentication(
                ownerId = binding.userId,
                deviceId = binding.deviceId,
                authRequiredState = OfflineOperationState.AUTH_REQUIRED.name,
                pendingState = OfflineOperationState.PENDING.name,
                maxAttempts = OfflineRetryPolicy.maxAttempts,
                at = now(),
            )
            synchronizeEligible()
        }
    }

    private suspend fun recoverInterruptedWork() {
        val timestamp = now()
        database.pendingOperations().recoverInterruptedSync(
            syncingState = OfflineOperationState.SYNCING.name,
            recoveredState = OfflineOperationState.RETRYABLE_FAILURE.name,
            at = timestamp,
            failureCategory = ErrorCategory.NETWORK_UNAVAILABLE.name,
            failureCode = "PROCESS_INTERRUPTED_DURING_SYNC",
        )
        database.pendingOperations().terminateExhaustedRetries(
            retryableState = OfflineOperationState.RETRYABLE_FAILURE.name,
            terminalState = OfflineOperationState.TERMINAL_FAILURE.name,
            maxAttempts = OfflineRetryPolicy.maxAttempts,
            at = timestamp,
            failureCategory = ErrorCategory.NETWORK_UNAVAILABLE.name,
            failureCode = "RETRY_LIMIT_REACHED_AFTER_RECOVERY",
        )
    }

    private suspend fun synchronizeEligible() = coordinationMutex.withLock {
        val binding = sessions.currentAuthorityBinding() ?: return@withLock
        val timestamp = now()
        database.pendingOperations().pruneTerminal(
            terminalStates = TERMINAL_STATES,
            cutoff = timestamp - OfflineCachePolicy.terminalRetentionMillis,
        )
        val operations = database.pendingOperations().eligibleForSync(
            ownerId = binding.userId,
            deviceId = binding.deviceId,
            eligibleStates = ELIGIBLE_STATES,
            maxAttempts = OfflineRetryPolicy.maxAttempts,
            at = timestamp,
            limit = OfflineCachePolicy.maxActiveOperations,
        )
        operations.forEach { scheduler.schedule(it.operationId) }
    }

    companion object {
        private val ELIGIBLE_STATES = listOf(
            OfflineOperationState.PENDING.name,
            OfflineOperationState.WAITING_FOR_NETWORK.name,
            OfflineOperationState.RETRYABLE_FAILURE.name,
        )
        private val TERMINAL_STATES = listOf(
            OfflineOperationState.ACKNOWLEDGED.name,
            OfflineOperationState.REJECTED.name,
            OfflineOperationState.CANCELLED.name,
            OfflineOperationState.TERMINAL_FAILURE.name,
        )
    }
}
