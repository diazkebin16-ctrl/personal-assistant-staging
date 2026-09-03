package com.personalassistant.android.auth

import androidx.work.WorkManager
import androidx.work.await
import com.personalassistant.android.data.local.AssistantDatabase

class LogoutCoordinator(
    private val sessionManager: SessionManager,
    private val database: AssistantDatabase,
    private val workManager: WorkManager,
) {
    suspend fun bindAuthenticated(binding: SessionAuthorityBinding) {
        val previous = sessionManager.currentAuthorityBinding()
        if (previous != binding) {
            workManager.cancelAllWorkByTag(USER_WORK_TAG).await()
            database.clearAllTables()
        }
        sessionManager.setAuthorityBinding(binding)
    }

    suspend fun logout() {
        workManager.cancelAllWorkByTag(USER_WORK_TAG).await()
        database.clearAllTables()
        sessionManager.logout()
    }

    suspend fun deviceRevoked() = logout()

    suspend fun authenticationExpired() {
        workManager.cancelAllWorkByTag(USER_WORK_TAG).await()
        sessionManager.clearCredentialsPreservingAuthority()
    }

    companion object { const val USER_WORK_TAG = "authenticated_delivery" }
}
