package com.personalassistant.android.wake

import android.annotation.SuppressLint
import android.content.Context
import com.personalassistant.shared.DefaultWakeProfileId
import com.personalassistant.shared.WakeActivationRecord
import com.personalassistant.shared.WakeActivationStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class WakePreferences(context: Context) : WakeActivationStore {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    val enabled: Boolean get() = preferences.getBoolean(ENABLED, false)
    val profileId: String get() = preferences.getString(PROFILE_ID, DefaultWakeProfileId)!!
    val conversationId: String? get() = preferences.getString(CONVERSATION_ID, null)

    fun saveOptIn(conversationId: String, profileId: String) {
        require(conversationId.isNotBlank())
        preferences.edit()
            .putBoolean(ENABLED, true)
            .putString(CONVERSATION_ID, conversationId)
            .putString(PROFILE_ID, profileId)
            .apply()
    }

    fun disable() {
        preferences.edit()
            .putBoolean(ENABLED, false)
            .remove(CONVERSATION_ID)
            .remove(LAST_ACTIVATION_ID)
            .remove(LAST_ACTIVATION_AT)
            .apply()
    }

    override suspend fun lastAccepted(): WakeActivationRecord? {
        val id = preferences.getString(LAST_ACTIVATION_ID, null) ?: return null
        val timestamp = preferences.getLong(LAST_ACTIVATION_AT, 0L)
        if (timestamp <= 0L) return null
        return WakeActivationRecord(id, timestamp)
    }

    // Replay protection must reach durable storage before the VoiceSession side effect begins.
    // A synchronous commit is intentional here, but it is confined to the IO dispatcher.
    @SuppressLint("ApplySharedPref")
    override suspend fun saveAccepted(record: WakeActivationRecord) = withContext(Dispatchers.IO) {
        val persisted = preferences.edit()
            .putString(LAST_ACTIVATION_ID, record.activationId)
            .putLong(LAST_ACTIVATION_AT, record.acceptedAtEpochMillis)
            .commit()
        check(persisted) { "Unable to persist wake activation replay protection" }
    }

    companion object {
        private const val PREFERENCES_NAME = "wake_device_preferences_v1"
        private const val ENABLED = "wake_enabled"
        private const val PROFILE_ID = "wake_profile_id"
        private const val CONVERSATION_ID = "wake_conversation_id"
        private const val LAST_ACTIVATION_ID = "wake_last_activation_id"
        private const val LAST_ACTIVATION_AT = "wake_last_activation_at"
    }
}
