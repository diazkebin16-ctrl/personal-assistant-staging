package com.personalassistant.android.data.local

import com.personalassistant.android.security.AndroidKeystoreCipher

class LocalContentCipher {
    private val cipher = AndroidKeystoreCipher("pa_local_content_v1")
    fun encrypt(content: String): ByteArray = cipher.encrypt(content.toByteArray(Charsets.UTF_8))
    fun decrypt(content: ByteArray): String = cipher.decrypt(content).toString(Charsets.UTF_8)
}

