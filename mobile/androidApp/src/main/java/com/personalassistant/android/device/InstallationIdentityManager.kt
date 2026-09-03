package com.personalassistant.android.device

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.personalassistant.android.security.EncryptedLocalStore
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.SecureRandom
import java.security.spec.ECGenParameterSpec

class InstallationIdentityManager(
    private val store: EncryptedLocalStore,
    private val random: SecureRandom = SecureRandom(),
) {
    suspend fun installationId(): String {
        store.get(INSTALLATION_ID)?.let { return it }
        val bytes = ByteArray(24).also(random::nextBytes)
        val generated = "android:" + Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        store.put(INSTALLATION_ID, generated)
        return generated
    }

    fun publicKeyPem(): String {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (!keyStore.containsAlias(DEVICE_KEY_ALIAS)) {
            KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore").run {
                initialize(
                    KeyGenParameterSpec.Builder(
                        DEVICE_KEY_ALIAS,
                        KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY,
                    ).setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                        .setDigests(KeyProperties.DIGEST_SHA256)
                        .setUserAuthenticationRequired(false)
                        .build(),
                )
                generateKeyPair()
            }
        }
        val encoded = keyStore.getCertificate(DEVICE_KEY_ALIAS).publicKey.encoded
        val body = Base64.encodeToString(encoded, Base64.NO_WRAP)
        return "-----BEGIN PUBLIC KEY-----\n$body\n-----END PUBLIC KEY-----"
    }

    companion object {
        private const val INSTALLATION_ID = "installation_id"
        private const val DEVICE_KEY_ALIAS = "pa_device_identity_v1"
    }
}

