package com.personalassistant.android.data.local

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import androidx.room.ColumnInfo

@Entity(tableName = "conversations")
data class ConversationEntity(
    @PrimaryKey val id: String,
    val deviceId: String?,
    val title: String?,
    val version: Int,
    val createdAt: String,
    val updatedAt: String,
    val lastMessageAt: String?,
)

@Entity(
    tableName = "messages",
    indices = [Index(value = ["conversationId", "sequence"], unique = true)],
)
data class MessageEntity(
    @PrimaryKey val id: String,
    val conversationId: String,
    val role: String,
    val status: String,
    val outcome: String?,
    val sequence: Int,
    val encryptedContent: ByteArray,
    val sensitivity: String,
    val confirmationRequestId: String?,
    val reasonCode: String?,
    val createdAt: String,
)

@Entity(
    tableName = "pending_operations",
    indices = [
        Index(value = ["idempotencyKey"], unique = true),
        Index(value = ["ownerId", "deviceId", "status"]),
    ],
)
data class PendingOperationEntity(
    @PrimaryKey val operationId: String,
    @ColumnInfo(defaultValue = "'TEXT_MESSAGE'") val operationType: String,
    val conversationId: String,
    val idempotencyKey: String,
    val encryptedPayload: ByteArray,
    @ColumnInfo(defaultValue = "''") val payloadFingerprint: String,
    @ColumnInfo(defaultValue = "1") val payloadVersion: Int,
    val expectedVersion: Int,
    @ColumnInfo(defaultValue = "''") val ownerId: String,
    @ColumnInfo(defaultValue = "''") val deviceId: String,
    val createdAtEpochMillis: Long,
    @ColumnInfo(defaultValue = "0") val updatedAtEpochMillis: Long,
    val attemptCount: Int,
    val lastAttemptAtEpochMillis: Long?,
    val nextAttemptAtEpochMillis: Long?,
    val serverAcknowledgedAtEpochMillis: Long?,
    val lastFailureCategory: String?,
    val lastFailureCode: String?,
    val status: String,
)
