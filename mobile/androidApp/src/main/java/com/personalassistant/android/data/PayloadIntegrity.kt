package com.personalassistant.android.data

import java.security.MessageDigest

internal object PayloadIntegrity {
    fun fingerprint(
        operationType: String,
        conversationId: String,
        idempotencyKey: String,
        expectedVersion: Int,
        content: String,
    ): String {
        val canonical = listOf(
            operationType,
            conversationId,
            idempotencyKey,
            expectedVersion.toString(),
            content,
        ).joinToString(separator = "") { "${it.length}:$it" }
        return MessageDigest.getInstance("SHA-256")
            .digest(canonical.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
    }
}
