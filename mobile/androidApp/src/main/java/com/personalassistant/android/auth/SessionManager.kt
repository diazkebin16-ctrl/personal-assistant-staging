package com.personalassistant.android.auth

import com.personalassistant.android.security.EncryptedLocalStore
import com.personalassistant.shared.ApiResult
import com.personalassistant.shared.SessionHeadersProvider
import com.personalassistant.shared.SupabaseAuthApi
import com.personalassistant.shared.SupabaseSessionResponse
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class SessionAuthorityBinding(val userId: String, val deviceId: String)

class SessionManager(
    private val store: EncryptedLocalStore,
    private val authApi: SupabaseAuthApi,
    private val epochSeconds: () -> Long = { System.currentTimeMillis() / 1000 },
) : SessionHeadersProvider {
    private val refreshMutex = Mutex()

    suspend fun signIn(email: String, password: String): ApiResult<Unit> = when (val result = authApi.signIn(email, password)) {
        is ApiResult.Success -> {
            persist(result.value)
            ApiResult.Success(Unit)
        }
        is ApiResult.Failure -> result
    }

    override suspend fun accessToken(): String? = refreshMutex.withLock {
        val token = store.get(ACCESS_TOKEN) ?: return@withLock null
        val expiresAt = store.get(EXPIRES_AT)?.toLongOrNull() ?: return@withLock null
        if (expiresAt - epochSeconds() > REFRESH_SKEW_SECONDS) return@withLock token
        val refreshToken = store.get(REFRESH_TOKEN) ?: return@withLock null
        when (val refreshed = authApi.refresh(refreshToken)) {
            is ApiResult.Success -> {
                persist(refreshed.value)
                refreshed.value.accessToken
            }
            is ApiResult.Failure -> if (expiresAt > epochSeconds()) token else null
        }
    }

    override suspend fun registeredDeviceId(): String? =
        currentAuthorityBinding()?.deviceId ?: store.get(LEGACY_DEVICE_ID)
    suspend fun currentAuthorityBinding(): SessionAuthorityBinding? {
        val encoded = store.get(AUTHORITY_BINDING) ?: return null
        val parts = encoded.split('|', limit = 2)
        if (parts.size != 2 || parts.any { it.isBlank() }) return null
        return SessionAuthorityBinding(parts[0], parts[1])
    }
    suspend fun setAuthorityBinding(binding: SessionAuthorityBinding) {
        require('|' !in binding.userId && '|' !in binding.deviceId)
        store.put(AUTHORITY_BINDING, "${binding.userId}|${binding.deviceId}")
        store.put(LEGACY_DEVICE_ID, binding.deviceId)
    }
    suspend fun hasSession(): Boolean = store.get(REFRESH_TOKEN) != null
    suspend fun clearCredentialsPreservingAuthority() {
        store.remove(ACCESS_TOKEN)
        store.remove(REFRESH_TOKEN)
        store.remove(EXPIRES_AT)
    }
    suspend fun logout() = store.clear()

    private suspend fun persist(session: SupabaseSessionResponse) {
        store.put(ACCESS_TOKEN, session.accessToken)
        store.put(REFRESH_TOKEN, session.refreshToken)
        store.put(EXPIRES_AT, (epochSeconds() + session.expiresIn).toString())
    }

    companion object {
        private const val ACCESS_TOKEN = "access_token"
        private const val REFRESH_TOKEN = "refresh_token"
        private const val EXPIRES_AT = "expires_at"
        private const val AUTHORITY_BINDING = "authority_binding_v1"
        private const val LEGACY_DEVICE_ID = "device_id"
        private const val REFRESH_SKEW_SECONDS = 60L
    }
}
