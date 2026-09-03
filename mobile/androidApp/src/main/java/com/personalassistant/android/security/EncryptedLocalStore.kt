package com.personalassistant.android.security

import android.content.Context
import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class EncryptedLocalStore(
    context: Context,
    namespace: String,
    keyAlias: String,
) {
    private val preferences = context.getSharedPreferences(namespace, Context.MODE_PRIVATE)
    private val cipher = AndroidKeystoreCipher(keyAlias)

    suspend fun put(key: String, value: String) = withContext(Dispatchers.IO) {
        val encrypted = cipher.encrypt(value.toByteArray(Charsets.UTF_8))
        check(preferences.edit().putString(key, Base64.encodeToString(encrypted, Base64.NO_WRAP)).commit())
    }

    suspend fun get(key: String): String? = withContext(Dispatchers.IO) {
        val encoded = preferences.getString(key, null) ?: return@withContext null
        runCatching {
            cipher.decrypt(Base64.decode(encoded, Base64.NO_WRAP)).toString(Charsets.UTF_8)
        }.getOrNull()
    }

    suspend fun remove(key: String) = withContext(Dispatchers.IO) {
        check(preferences.edit().remove(key).commit())
    }

    suspend fun clear() = withContext(Dispatchers.IO) {
        check(preferences.edit().clear().commit())
    }
}

