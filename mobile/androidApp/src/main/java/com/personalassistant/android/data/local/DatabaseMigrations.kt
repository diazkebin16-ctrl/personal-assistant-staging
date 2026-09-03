package com.personalassistant.android.data.local

import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

val MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(database: SupportSQLiteDatabase) {
        database.execSQL("ALTER TABLE pending_operations ADD COLUMN operationType TEXT NOT NULL DEFAULT 'TEXT_MESSAGE'")
        database.execSQL("ALTER TABLE pending_operations ADD COLUMN payloadFingerprint TEXT NOT NULL DEFAULT ''")
        database.execSQL("ALTER TABLE pending_operations ADD COLUMN payloadVersion INTEGER NOT NULL DEFAULT 1")
        database.execSQL("ALTER TABLE pending_operations ADD COLUMN ownerId TEXT NOT NULL DEFAULT ''")
        database.execSQL("ALTER TABLE pending_operations ADD COLUMN deviceId TEXT NOT NULL DEFAULT ''")
        database.execSQL("ALTER TABLE pending_operations ADD COLUMN updatedAtEpochMillis INTEGER NOT NULL DEFAULT 0")
        database.execSQL("ALTER TABLE pending_operations ADD COLUMN nextAttemptAtEpochMillis INTEGER")
        database.execSQL("ALTER TABLE pending_operations ADD COLUMN serverAcknowledgedAtEpochMillis INTEGER")
        database.execSQL("ALTER TABLE pending_operations ADD COLUMN lastFailureCategory TEXT")
        database.execSQL("ALTER TABLE pending_operations ADD COLUMN lastFailureCode TEXT")
        database.execSQL(
            "UPDATE pending_operations SET updatedAtEpochMillis = createdAtEpochMillis, " +
                "status = CASE status " +
                "WHEN 'WAITING_CONNECTION' THEN 'WAITING_FOR_NETWORK' " +
                "WHEN 'IN_FLIGHT' THEN 'RETRYABLE_FAILURE' " +
                "WHEN 'SUCCEEDED' THEN 'ACKNOWLEDGED' " +
                "WHEN 'FAILED' THEN 'TERMINAL_FAILURE' ELSE status END",
        )
        // Phase 8 records predate owner/device binding and cannot be replayed safely after upgrade.
        database.execSQL(
                "UPDATE pending_operations SET status = 'REJECTED', " +
                "lastFailureCategory = 'AUTHORIZATION', lastFailureCode = 'LEGACY_IDENTITY_UNBOUND' " +
                "WHERE (ownerId = '' OR deviceId = '') " +
                "AND status NOT IN ('ACKNOWLEDGED', 'CANCELLED', 'TERMINAL_FAILURE', 'REJECTED')",
        )
        database.execSQL(
            "CREATE INDEX IF NOT EXISTS index_pending_operations_ownerId_deviceId_status " +
                "ON pending_operations(ownerId, deviceId, status)",
        )
    }
}
