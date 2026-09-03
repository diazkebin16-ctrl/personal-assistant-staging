package com.personalassistant.android.data

import android.os.Build
import com.personalassistant.android.auth.SessionAuthorityBinding
import com.personalassistant.android.device.AndroidCapabilities
import com.personalassistant.android.device.InstallationIdentityManager
import com.personalassistant.shared.ApiResult
import com.personalassistant.shared.BackendApiClient
import com.personalassistant.shared.DeviceRegistrationRequest

class DeviceRepository(
    private val api: BackendApiClient,
    private val identity: InstallationIdentityManager,
    private val capabilities: AndroidCapabilities,
) {
    suspend fun register(): ApiResult<SessionAuthorityBinding> {
        val request = DeviceRegistrationRequest(
            deviceName = Build.MODEL.take(100).ifBlank { "Android device" },
            platform = "android-${Build.VERSION.SDK_INT}",
            deviceIdentifier = identity.installationId(),
            capabilities = capabilities.registrationManifest(),
            publicKey = identity.publicKeyPem(),
        )
        return when (val result = api.registerDevice(request)) {
            is ApiResult.Success -> {
                val registeredDeviceId = result.value.id
                // The authoritative identity endpoint binds the authenticated user and device.
                // Client registration fields never establish ownership by themselves.
                when (val identityResult = api.meForRegisteredDevice(registeredDeviceId)) {
                    is ApiResult.Success -> {
                        val identity = identityResult.value
                        if (!identity.authenticated || identity.deviceId != registeredDeviceId) {
                            ApiResult.Failure(
                                com.personalassistant.shared.ErrorCategory.CONFLICT,
                                "IDENTITY_BINDING_CONFLICT",
                                false,
                            )
                        } else {
                            ApiResult.Success(SessionAuthorityBinding(identity.userId, registeredDeviceId))
                        }
                    }
                    is ApiResult.Failure -> identityResult
                }
            }
            is ApiResult.Failure -> result
        }
    }
}
