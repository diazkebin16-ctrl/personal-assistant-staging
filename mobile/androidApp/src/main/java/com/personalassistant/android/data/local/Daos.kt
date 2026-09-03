package com.personalassistant.android.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

@Dao
interface ConversationDao {
    @Query("SELECT * FROM conversations ORDER BY COALESCE(lastMessageAt, createdAt) DESC")
    fun observeAll(): Flow<List<ConversationEntity>>

    @Query("SELECT * FROM conversations WHERE id = :id")
    suspend fun get(id: String): ConversationEntity?

    @Upsert suspend fun upsert(item: ConversationEntity)
    @Upsert suspend fun upsertAll(items: List<ConversationEntity>)
}

@Dao
interface MessageDao {
    @Query("SELECT * FROM messages WHERE conversationId = :conversationId ORDER BY sequence")
    fun observe(conversationId: String): Flow<List<MessageEntity>>

    @Upsert suspend fun upsertAll(items: List<MessageEntity>)

    @Query(
        "DELETE FROM messages WHERE conversationId = :conversationId AND id NOT IN " +
            "(SELECT id FROM messages WHERE conversationId = :conversationId ORDER BY sequence DESC LIMIT :keep)",
    )
    suspend fun pruneConversation(conversationId: String, keep: Int)
}

@Dao
interface PendingOperationDao {
    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(item: PendingOperationEntity)

    @Query("SELECT * FROM pending_operations WHERE operationId = :operationId")
    suspend fun get(operationId: String): PendingOperationEntity?

    @Query(
        "SELECT COUNT(*) FROM pending_operations WHERE ownerId = :ownerId AND status NOT IN (:terminalStates)",
    )
    suspend fun activeCount(ownerId: String, terminalStates: List<String>): Int

    @Query(
        "UPDATE pending_operations SET status = :syncingState, attemptCount = attemptCount + 1, " +
            "lastAttemptAtEpochMillis = :at, updatedAtEpochMillis = :at, " +
            "nextAttemptAtEpochMillis = NULL, lastFailureCategory = NULL, lastFailureCode = NULL " +
            "WHERE operationId = :operationId AND ownerId = :ownerId AND deviceId = :deviceId " +
            "AND status IN (:eligibleStates) AND attemptCount < :maxAttempts",
    )
    suspend fun claimForSync(
        operationId: String,
        ownerId: String,
        deviceId: String,
        eligibleStates: List<String>,
        syncingState: String,
        maxAttempts: Int,
        at: Long,
    ): Int

    @Query(
        "UPDATE pending_operations SET status = :toState, updatedAtEpochMillis = :at, " +
            "nextAttemptAtEpochMillis = :nextAttemptAt, lastFailureCategory = :failureCategory, " +
            "lastFailureCode = :failureCode WHERE operationId = :operationId AND status IN (:fromStates)",
    )
    suspend fun transition(
        operationId: String,
        fromStates: List<String>,
        toState: String,
        at: Long,
        nextAttemptAt: Long?,
        failureCategory: String?,
        failureCode: String?,
    ): Int

    @Query(
        "UPDATE pending_operations SET status = :acknowledgedState, updatedAtEpochMillis = :at, " +
            "serverAcknowledgedAtEpochMillis = :at, nextAttemptAtEpochMillis = NULL, " +
            "lastFailureCategory = NULL, lastFailureCode = NULL " +
            "WHERE operationId = :operationId AND status IN (:fromStates)",
    )
    suspend fun acknowledge(
        operationId: String,
        fromStates: List<String>,
        acknowledgedState: String,
        at: Long,
    ): Int

    @Query(
        "UPDATE pending_operations SET status = :recoveredState, updatedAtEpochMillis = :at, " +
            "nextAttemptAtEpochMillis = :at, lastFailureCategory = :failureCategory, " +
            "lastFailureCode = :failureCode WHERE status = :syncingState",
    )
    suspend fun recoverInterruptedSync(
        syncingState: String,
        recoveredState: String,
        at: Long,
        failureCategory: String,
        failureCode: String,
    ): Int

    @Query(
        "UPDATE pending_operations SET status = :terminalState, updatedAtEpochMillis = :at, " +
            "nextAttemptAtEpochMillis = NULL, lastFailureCategory = :failureCategory, " +
            "lastFailureCode = :failureCode WHERE status = :retryableState " +
            "AND attemptCount >= :maxAttempts",
    )
    suspend fun terminateExhaustedRetries(
        retryableState: String,
        terminalState: String,
        maxAttempts: Int,
        at: Long,
        failureCategory: String,
        failureCode: String,
    ): Int

    @Query(
        "SELECT * FROM pending_operations WHERE ownerId = :ownerId AND deviceId = :deviceId " +
            "AND status IN (:eligibleStates) AND attemptCount < :maxAttempts " +
            "AND (nextAttemptAtEpochMillis IS NULL OR nextAttemptAtEpochMillis <= :at) " +
            "ORDER BY createdAtEpochMillis, operationId LIMIT :limit",
    )
    suspend fun eligibleForSync(
        ownerId: String,
        deviceId: String,
        eligibleStates: List<String>,
        maxAttempts: Int,
        at: Long,
        limit: Int,
    ): List<PendingOperationEntity>

    @Query(
        "UPDATE pending_operations SET status = :pendingState, updatedAtEpochMillis = :at, " +
            "nextAttemptAtEpochMillis = NULL, lastFailureCategory = NULL, lastFailureCode = NULL " +
            "WHERE ownerId = :ownerId AND deviceId = :deviceId AND status = :authRequiredState " +
            "AND attemptCount < :maxAttempts",
    )
    suspend fun resumeAfterAuthentication(
        ownerId: String,
        deviceId: String,
        authRequiredState: String,
        pendingState: String,
        maxAttempts: Int,
        at: Long,
    ): Int

    @Query(
        "DELETE FROM pending_operations WHERE status IN (:terminalStates) AND updatedAtEpochMillis < :cutoff",
    )
    suspend fun pruneTerminal(terminalStates: List<String>, cutoff: Long): Int

    @Query("SELECT * FROM pending_operations ORDER BY createdAtEpochMillis")
    fun observeAll(): Flow<List<PendingOperationEntity>>
}
