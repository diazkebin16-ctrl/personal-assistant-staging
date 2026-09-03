package com.personalassistant.android.data.local

import androidx.room.Database
import androidx.room.RoomDatabase

@Database(
    entities = [ConversationEntity::class, MessageEntity::class, PendingOperationEntity::class],
    version = 2,
    exportSchema = true,
)
abstract class AssistantDatabase : RoomDatabase() {
    abstract fun conversations(): ConversationDao
    abstract fun messages(): MessageDao
    abstract fun pendingOperations(): PendingOperationDao
}
