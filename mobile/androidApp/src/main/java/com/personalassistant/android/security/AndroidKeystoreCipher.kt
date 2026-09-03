package com.personalassistant.android.security

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.nio.ByteBuffer
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class AndroidKeystoreCipher(private val alias: String) {
    private val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    fun encrypt(plainText: ByteArray): ByteArray {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val ciphertext = cipher.doFinal(plainText)
        return ByteBuffer.allocate(4 + cipher.iv.size + ciphertext.size)
            .putInt(cipher.iv.size)
            .put(cipher.iv)
            .put(ciphertext)
            .array()
    }

    fun decrypt(envelope: ByteArray): ByteArray {
        val buffer = ByteBuffer.wrap(envelope)
        val ivLength = buffer.int
        require(ivLength in 12..16 && buffer.remaining() > ivLength) { "Invalid encrypted envelope" }
        val iv = ByteArray(ivLength).also(buffer::get)
        val ciphertext = ByteArray(buffer.remaining()).also(buffer::get)
        return Cipher.getInstance(TRANSFORMATION).run {
            init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
            doFinal(ciphertext)
        }
    }

    private fun key(): SecretKey {
        (keyStore.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").run {
            init(
                KeyGenParameterSpec.Builder(
                    alias,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                ).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256)
                    .setRandomizedEncryptionRequired(true)
                    .build(),
            )
            generateKey()
        }
    }

    companion object { private const val TRANSFORMATION = "AES/GCM/NoPadding" }
}

