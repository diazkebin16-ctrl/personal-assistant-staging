package com.personalassistant.android.data

import androidx.room.withTransaction
import com.personalassistant.android.auth.SessionManager
import com.personalassistant.android.connectivity.ConnectivityCoordinator
import com.personalassistant.android.data.local.AssistantDatabase
import com.personalassistant.android.data.local.ConversationEntity
import com.personalassistant.android.data.local.LocalContentCipher
import com.personalassistant.android.data.local.MessageEntity
import com.personalassistant.android.data.local.PendingOperationEntity
import com.personalassistant.android.work.DeliveryScheduler
import com.personalassistant.shared.ApiResult
import com.personalassistant.shared.AssistantRequest
import com.personalassistant.shared.AssistantResponse
import com.personalassistant.shared.BackendApiClient
import com.personalassistant.shared.ConversationCreateRequest
import com.personalassistant.shared.ConversationMessageResponse
import com.personalassistant.shared.ConversationResponse
import com.personalassistant.shared.ConnectivityState
import com.personalassistant.shared.DataSensitivity
import com.personalassistant.shared.ErrorCategory
import com.personalassistant.shared.OfflineCachePolicy
import com.personalassistant.shared.OfflineFailure
import com.personalassistant.shared.OfflineFailureClassifier
import com.personalassistant.shared.OfflineFailureDisposition
import com.personalassistant.shared.OfflineOperationState
import com.personalassistant.shared.OfflineOperationStateMachine
import com.personalassistant.shared.OfflineRetryPolicy
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import java.util.UUID

class ConversationRepository(
    private val api: BackendApiClient,
    private val database: AssistantDatabase,
    private val contentCipher: LocalContentCipher,
    private val scheduler: DeliveryScheduler,
    private val sessions: SessionManager,
    private val connectivity: ConnectivityCoordinator,
    private val onDeviceRevoked: suspend () -> Unit,
    private val now: () -> Long = System::currentTimeMillis,
) {
    fun conversations(): Flow<List<ConversationEntity>> = database.conversations().observeAll()

    fun messages(conversationId: String): Flow<List<CachedMessage>> =
        combine(database.messages().observe(conversationId), connectivity.state) { records, state ->
            val stale = state != ConnectivityState.ONLINE
            records.map {
                val sensitiveHidden = stale && it.sensitivity == DataSensitivity.CRITICAL.name
                CachedMessage(
                    id = it.id,
                    role = it.role,
                    status = it.status,
                    outcome = it.outcome,
                    sequence = it.sequence,
                    content = if (sensitiveHidden) {
                        "Sensitive cached message hidden until the server connection is verified"
                    } else {
                        runCatching { contentCipher.decrypt(it.encryptedContent) }
                            .getOrDefault("Message unavailable")
                    },
                    isStale = stale,
                    sensitiveContentHidden = sensitiveHidden,
                    confirmationRequestId = it.confirmationRequestId,
                    reasonCode = it.reasonCode,
                )
            }
        }

    fun pendingOperations(): Flow<List<PendingOperationEntity>> =
        database.pendingOperations().observeAll()

    suspend fun refreshConversations(): ApiResult<Unit> = when (val result = api.conversations()) {
        is ApiResult.Success -> {
            connectivity.reportBackendSuccess()
            database.conversations().upsertAll(result.value.map(::conversationEntity))
            ApiResult.Success(Unit)
        }
        is ApiResult.Failure -> {
            connectivity.reportBackendFailure(result.category)
            result
        }
    }

    suspend fun createConversation(title: String?): ApiResult<ConversationEntity> =
        when (val result = api.createConversation(ConversationCreateRequest(title))) {
            is ApiResult.Success -> {
                connectivity.reportBackendSuccess()
                val entity = conversationEntity(result.value)
                database.conversations().upsert(entity)
                ApiResult.Success(entity)
            }
            is ApiResult.Failure -> {
                connectivity.reportBackendFailure(result.category)
                result
            }
        }

    suspend fun refreshMessages(conversationId: String): ApiResult<Unit> =
        when (val result = api.messages(conversationId)) {
            is ApiResult.Success -> {
                connectivity.reportBackendSuccess()
                database.withTransaction {
                    database.messages().upsertAll(result.value.map(::messageEntity))
                    database.messages().pruneConversation(
                        conversationId,
                        OfflineCachePolicy.maxMessagesPerConversation,
                    )
                }
                ApiResult.Success(Unit)
            }
            is ApiResult.Failure -> {
                connectivity.reportBackendFailure(result.category)
                result
            }
        }

    suspend fun approveConfirmation(confirmationId: String): ApiResult<Unit> =
        when (val result = api.approveConfirmation(confirmationId)) {
            is ApiResult.Success -> {
                connectivity.reportBackendSuccess()
                ApiResult.Success(Unit)
            }
            is ApiResult.Failure -> {
                connectivity.reportBackendFailure(result.category)
                result
            }
        }

    suspend fun enqueueMessage(
        conversationId: String,
        content: String,
        expectedVersion: Int,
    ): EnqueueResult {
        if (conversationId.isBlank() || content.isBlank() || content.length > 50_000 || expectedVersion < 1) {
            return EnqueueResult.InvalidRequest
        }
        val binding = sessions.currentAuthorityBinding() ?: return EnqueueResult.AuthenticationRequired
        val dao = database.pendingOperations()
        if (dao.activeCount(binding.userId, TERMINAL_STATES) >= OfflineCachePolicy.maxActiveOperations) {
            return EnqueueResult.QueueFull
        }
        val operationId = UUID.randomUUID().toString()
        val idempotencyKey = "android:$operationId"
        val createdAt = now()
        val encryptedPayload = try {
            contentCipher.encrypt(content)
        } catch (_: RuntimeException) {
            return EnqueueResult.LocalStorageFailure
        }
        val initialState = if (connectivity.state.value == ConnectivityState.ONLINE) {
            OfflineOperationState.PENDING
        } else {
            OfflineOperationState.WAITING_FOR_NETWORK
        }
        val operation = PendingOperationEntity(
            operationId = operationId,
            operationType = TEXT_MESSAGE_OPERATION,
            conversationId = conversationId,
            idempotencyKey = idempotencyKey,
            encryptedPayload = encryptedPayload,
            payloadFingerprint = PayloadIntegrity.fingerprint(
                TEXT_MESSAGE_OPERATION,
                conversationId,
                idempotencyKey,
                expectedVersion,
                content,
            ),
            payloadVersion = CURRENT_PAYLOAD_VERSION,
            expectedVersion = expectedVersion,
            ownerId = binding.userId,
            deviceId = binding.deviceId,
            createdAtEpochMillis = createdAt,
            updatedAtEpochMillis = createdAt,
            attemptCount = 0,
            lastAttemptAtEpochMillis = null,
            nextAttemptAtEpochMillis = null,
            serverAcknowledgedAtEpochMillis = null,
            lastFailureCategory = null,
            lastFailureCode = null,
            status = initialState.name,
        )
        try {
            dao.insert(operation)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: RuntimeException) {
            return EnqueueResult.LocalStorageFailure
        }
        // Persistence is authoritative for local pending intent. Scheduling may be reconstructed.
        try {
            scheduler.schedule(operation.operationId)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: RuntimeException) {
            // The durable row remains recoverable by OfflineSyncCoordinator after local scheduler failure.
        }
        return EnqueueResult.Queued(operation.operationId)
    }

    /** Re-enqueue the same durable identity; network delivery remains worker-only. */
    suspend fun retryDelivery(operationId: String): RetryScheduleResult {
        val operation = database.pendingOperations().get(operationId)
            ?: return RetryScheduleResult.NotFound
        val binding = sessions.currentAuthorityBinding() ?: return RetryScheduleResult.AuthenticationRequired
        if (operation.ownerId != binding.userId || operation.deviceId != binding.deviceId) {
            return RetryScheduleResult.IdentityMismatch
        }
        val state = operation.stateOrNull() ?: return RetryScheduleResult.Terminal
        if (state !in MANUAL_RETRY_STATES || operation.attemptCount >= OfflineRetryPolicy.maxAttempts) {
            return RetryScheduleResult.Terminal
        }
        scheduler.schedule(operation.operationId)
        return RetryScheduleResult.Scheduled
    }

    suspend fun cancel(operationId: String): CancellationResult {
        val operation = database.pendingOperations().get(operationId)
            ?: return CancellationResult.NotFound
        val binding = sessions.currentAuthorityBinding() ?: return CancellationResult.AuthenticationRequired
        if (operation.ownerId != binding.userId || operation.deviceId != binding.deviceId) {
            return CancellationResult.IdentityMismatch
        }
        operation.stateOrNull() ?: return CancellationResult.AlreadyTerminal
        val timestamp = now()
        val cancelled = database.pendingOperations().transition(
            operationId = operation.operationId,
            fromStates = CANCELLABLE_BEFORE_SYNC.map { it.name },
            toState = OfflineOperationState.CANCELLED.name,
            at = timestamp,
            nextAttemptAt = null,
            failureCategory = null,
            failureCode = "CANCELLED_BY_USER",
        )
        if (cancelled == 1) {
            scheduler.cancel(operation.operationId)
            return CancellationResult.CancelledLocally
        }
        OfflineOperationStateMachine.requireTransition(
            OfflineOperationState.SYNCING,
            OfflineOperationState.CANCEL_REQUESTED,
        )
        val requested = database.pendingOperations().transition(
            operationId = operation.operationId,
            fromStates = listOf(OfflineOperationState.SYNCING.name),
            toState = OfflineOperationState.CANCEL_REQUESTED.name,
            at = timestamp,
            nextAttemptAt = null,
            failureCategory = null,
            failureCode = "SERVER_RESULT_PENDING",
        )
        return if (requested == 1) CancellationResult.ServerResultPending
        else CancellationResult.AlreadyTerminal
    }

    /** Internal delivery boundary invoked only by MessageDeliveryWorker. */
    internal suspend fun deliver(operationId: String): DeliveryResult {
        val dao = database.pendingOperations()
        val operation = dao.get(operationId) ?: return DeliveryResult.TerminalFailure
        val initialState = operation.stateOrNull() ?: return DeliveryResult.TerminalFailure
        if (initialState in TERMINAL_STATE_VALUES || initialState == OfflineOperationState.CANCEL_REQUESTED) {
            return if (initialState == OfflineOperationState.ACKNOWLEDGED) DeliveryResult.Success
            else DeliveryResult.TerminalFailure
        }
        if (operation.attemptCount >= OfflineRetryPolicy.maxAttempts) {
            transitionFromActive(
                operationId,
                OfflineOperationState.TERMINAL_FAILURE,
                ErrorCategory.NETWORK_UNAVAILABLE,
                "RETRY_LIMIT_REACHED",
            )
            return DeliveryResult.TerminalFailure
        }
        val binding = sessions.currentAuthorityBinding()
        if (binding == null) {
            transitionFromActive(operationId, OfflineOperationState.AUTH_REQUIRED, ErrorCategory.AUTHENTICATION, "AUTH_REQUIRED")
            return DeliveryResult.AuthenticationRequired
        }
        if (operation.ownerId != binding.userId || operation.deviceId != binding.deviceId) {
            transitionFromActive(operationId, OfflineOperationState.REJECTED, ErrorCategory.AUTHORIZATION, "IDENTITY_BINDING_MISMATCH")
            return DeliveryResult.TerminalFailure
        }
        val content = runCatching { contentCipher.decrypt(operation.encryptedPayload) }.getOrElse {
            transitionFromActive(operationId, OfflineOperationState.TERMINAL_FAILURE, ErrorCategory.VALIDATION, "PAYLOAD_AUTHENTICATION_FAILED")
            return DeliveryResult.TerminalFailure
        }
        if (!operation.hasValidEnvelope(content)) {
            transitionFromActive(operationId, OfflineOperationState.TERMINAL_FAILURE, ErrorCategory.VALIDATION, "PAYLOAD_INTEGRITY_FAILED")
            return DeliveryResult.TerminalFailure
        }
        val claimed = dao.claimForSync(
            operationId = operation.operationId,
            ownerId = binding.userId,
            deviceId = binding.deviceId,
            eligibleStates = WORKER_CLAIM_STATES.map { it.name },
            syncingState = OfflineOperationState.SYNCING.name,
            maxAttempts = OfflineRetryPolicy.maxAttempts,
            at = now(),
        )
        if (claimed != 1) {
            val current = dao.get(operationId)?.stateOrNull()
            return if (current == OfflineOperationState.ACKNOWLEDGED) DeliveryResult.Success
            else DeliveryResult.NoWork
        }
        val claimedOperation = dao.get(operationId) ?: return DeliveryResult.TerminalFailure
        val request = AssistantRequest(
            content = content,
            idempotencyKey = claimedOperation.idempotencyKey,
            expectedVersion = claimedOperation.expectedVersion,
        )
        return when (val response = api.submitMessage(claimedOperation.conversationId, request)) {
            is ApiResult.Success -> {
                connectivity.reportBackendSuccess()
                try {
                    database.withTransaction {
                        cache(response.value)
                        OfflineOperationStateMachine.requireTransition(
                            OfflineOperationState.SYNCING,
                            OfflineOperationState.ACKNOWLEDGED,
                        )
                        dao.acknowledge(
                            operationId,
                            listOf(
                                OfflineOperationState.SYNCING.name,
                                OfflineOperationState.CANCEL_REQUESTED.name,
                            ),
                            OfflineOperationState.ACKNOWLEDGED.name,
                            now(),
                        )
                    }
                    DeliveryResult.Success
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (_: RuntimeException) {
                    if (claimedOperation.attemptCount < OfflineRetryPolicy.maxAttempts) {
                        transitionFromSync(
                            operationId,
                            OfflineOperationState.RETRYABLE_FAILURE,
                            ErrorCategory.INTERNAL,
                            "LOCAL_ACK_COMMIT_FAILED",
                            now() + OfflineRetryPolicy.backoffMillis(
                                claimedOperation.attemptCount,
                                operationId,
                            ),
                        )
                        DeliveryResult.Retry
                    } else {
                        transitionFromSync(
                            operationId,
                            OfflineOperationState.TERMINAL_FAILURE,
                            ErrorCategory.INTERNAL,
                            "LOCAL_ACK_COMMIT_RETRY_EXHAUSTED",
                        )
                        DeliveryResult.TerminalFailure
                    }
                }
            }
            is ApiResult.Failure -> {
                connectivity.reportBackendFailure(response.category)
                handleFailure(operationId, claimedOperation.attemptCount, response)
            }
        }
    }

    private suspend fun handleFailure(
        operationId: String,
        attemptCount: Int,
        failure: ApiResult.Failure,
    ): DeliveryResult {
        if (database.pendingOperations().get(operationId)?.stateOrNull() == OfflineOperationState.CANCEL_REQUESTED) {
            // The request may have reached the server. Never fabricate local cancellation or replay it.
            return DeliveryResult.TerminalFailure
        }
        val disposition = OfflineFailureClassifier.classify(
            OfflineFailure(failure.category, failure.code, failure.retryable),
        )
        return when (disposition) {
            OfflineFailureDisposition.RETRYABLE -> {
                if (OfflineRetryPolicy.mayRetry(disposition, attemptCount)) {
                    val delay = OfflineRetryPolicy.backoffMillis(attemptCount, operationId)
                    transitionFromSync(
                        operationId,
                        OfflineOperationState.RETRYABLE_FAILURE,
                        failure.category,
                        failure.code,
                        now() + delay,
                    )
                    DeliveryResult.Retry
                } else {
                    transitionFromSync(
                        operationId,
                        OfflineOperationState.TERMINAL_FAILURE,
                        failure.category,
                        failure.code ?: "RETRY_LIMIT_REACHED",
                    )
                    DeliveryResult.TerminalFailure
                }
            }
            OfflineFailureDisposition.AUTH_REQUIRED -> {
                transitionFromSync(operationId, OfflineOperationState.AUTH_REQUIRED, failure.category, failure.code)
                DeliveryResult.AuthenticationRequired
            }
            OfflineFailureDisposition.DEVICE_REVOKED -> {
                transitionFromSync(operationId, OfflineOperationState.REJECTED, failure.category, failure.code)
                onDeviceRevoked()
                DeliveryResult.TerminalFailure
            }
            OfflineFailureDisposition.REJECTED,
            OfflineFailureDisposition.CONFLICT,
            -> {
                transitionFromSync(operationId, OfflineOperationState.REJECTED, failure.category, failure.code)
                DeliveryResult.TerminalFailure
            }
            OfflineFailureDisposition.TERMINAL -> {
                transitionFromSync(operationId, OfflineOperationState.TERMINAL_FAILURE, failure.category, failure.code)
                DeliveryResult.TerminalFailure
            }
        }
    }

    private suspend fun transitionFromSync(
        operationId: String,
        state: OfflineOperationState,
        category: ErrorCategory,
        code: String?,
        nextAttemptAt: Long? = null,
    ) {
        OfflineOperationStateMachine.requireTransition(OfflineOperationState.SYNCING, state)
        database.pendingOperations().transition(
            operationId,
            listOf(OfflineOperationState.SYNCING.name),
            state.name,
            now(),
            nextAttemptAt,
            category.name,
            code,
        )
    }

    private suspend fun transitionFromActive(
        operationId: String,
        state: OfflineOperationState,
        category: ErrorCategory,
        code: String,
    ) {
        val allowedFromStates = ACTIVE_PRE_SYNC_STATES.filter {
            it != state && OfflineOperationStateMachine.canTransition(it, state)
        }
        if (allowedFromStates.isEmpty()) return
        database.pendingOperations().transition(
            operationId,
            allowedFromStates.map { it.name },
            state.name,
            now(),
            null,
            category.name,
            code,
        )
    }

    private fun PendingOperationEntity.hasValidEnvelope(content: String): Boolean {
        if (operationType != TEXT_MESSAGE_OPERATION || payloadVersion != CURRENT_PAYLOAD_VERSION) return false
        if (idempotencyKey != "android:$operationId") return false
        return payloadFingerprint == PayloadIntegrity.fingerprint(
            operationType,
            conversationId,
            idempotencyKey,
            expectedVersion,
            content,
        )
    }

    private fun PendingOperationEntity.stateOrNull(): OfflineOperationState? =
        runCatching { OfflineOperationState.valueOf(status) }.getOrNull()

    private suspend fun cache(response: AssistantResponse) {
        database.conversations().upsert(conversationEntity(response.conversation))
        database.messages().upsertAll(
            listOf(messageEntity(response.userMessage), messageEntity(response.assistantMessage)),
        )
        database.messages().pruneConversation(
            response.conversation.id,
            OfflineCachePolicy.maxMessagesPerConversation,
        )
    }

    private fun conversationEntity(value: ConversationResponse) = ConversationEntity(
        value.id,
        value.deviceId,
        value.title,
        value.version,
        value.createdAt,
        value.updatedAt,
        value.lastMessageAt,
    )

    private fun messageEntity(value: ConversationMessageResponse) = MessageEntity(
        value.id,
        value.conversationId,
        value.role.name,
        value.status.name,
        value.outcome?.name,
        value.sequence,
        contentCipher.encrypt(value.content),
        value.sensitivity.name,
        value.confirmationRequestId,
        value.reasonCode,
        value.createdAt,
    )

    sealed interface DeliveryResult {
        data object Success : DeliveryResult
        data object Retry : DeliveryResult
        data object AuthenticationRequired : DeliveryResult
        data object NoWork : DeliveryResult
        data object TerminalFailure : DeliveryResult
    }

    sealed interface EnqueueResult {
        data class Queued(val operationId: String) : EnqueueResult
        data object AuthenticationRequired : EnqueueResult
        data object QueueFull : EnqueueResult
        data object InvalidRequest : EnqueueResult
        data object LocalStorageFailure : EnqueueResult
    }

    sealed interface RetryScheduleResult {
        data object Scheduled : RetryScheduleResult
        data object NotFound : RetryScheduleResult
        data object AuthenticationRequired : RetryScheduleResult
        data object IdentityMismatch : RetryScheduleResult
        data object Terminal : RetryScheduleResult
    }

    sealed interface CancellationResult {
        data object CancelledLocally : CancellationResult
        data object ServerResultPending : CancellationResult
        data object NotFound : CancellationResult
        data object AuthenticationRequired : CancellationResult
        data object IdentityMismatch : CancellationResult
        data object AlreadyTerminal : CancellationResult
    }

    data class CachedMessage(
        val id: String,
        val role: String,
        val status: String,
        val outcome: String?,
        val sequence: Int,
        val content: String,
        val isStale: Boolean,
        val sensitiveContentHidden: Boolean,
        val confirmationRequestId: String?,
        val reasonCode: String?,
    )

    companion object {
        const val TEXT_MESSAGE_OPERATION = "TEXT_MESSAGE"
        const val CURRENT_PAYLOAD_VERSION = 1
        const val MAX_ATTEMPTS = OfflineRetryPolicy.maxAttempts

        private val TERMINAL_STATE_VALUES = setOf(
            OfflineOperationState.ACKNOWLEDGED,
            OfflineOperationState.REJECTED,
            OfflineOperationState.CANCELLED,
            OfflineOperationState.TERMINAL_FAILURE,
        )
        private val TERMINAL_STATES = TERMINAL_STATE_VALUES.map { it.name }
        private val ACTIVE_PRE_SYNC_STATES = setOf(
            OfflineOperationState.PENDING,
            OfflineOperationState.WAITING_FOR_NETWORK,
            OfflineOperationState.RETRYABLE_FAILURE,
            OfflineOperationState.AUTH_REQUIRED,
        )
        private val WORKER_CLAIM_STATES = ACTIVE_PRE_SYNC_STATES
        private val MANUAL_RETRY_STATES = ACTIVE_PRE_SYNC_STATES
        private val CANCELLABLE_BEFORE_SYNC = ACTIVE_PRE_SYNC_STATES
    }
}
