package com.personalassistant.android.device

import com.personalassistant.shared.CapabilityName
import com.personalassistant.shared.CapabilityState

class AndroidCapabilities {
    fun registrationManifest(): Map<String, Boolean> = mapOf(
        "device_state" to true,
        "share" to true,
        "notifications" to false,
        "location" to false,
        "calendar_read" to false,
        "calendar_write" to false,
        "contacts_read" to false,
        // Hardware/API support only. This does not represent OS or Assistant permission.
        "microphone" to true,
        "camera" to false,
        "files" to false,
        "clipboard" to false,
    )

    fun state(
        capability: CapabilityName,
        osPermissionGranted: Boolean,
        assistantPermissionGranted: Boolean,
        actionAuthorized: Boolean,
    ): CapabilityState = CapabilityState(
        name = capability,
        deviceSupports = registrationManifest()[capability.name.lowercase()] == true,
        osPermissionGranted = osPermissionGranted,
        assistantPermissionGranted = assistantPermissionGranted,
        actionAuthorized = actionAuthorized,
    )
}
