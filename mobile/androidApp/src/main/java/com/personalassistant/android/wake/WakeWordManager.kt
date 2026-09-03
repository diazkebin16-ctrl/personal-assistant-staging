package com.personalassistant.android.wake

import android.Manifest
import android.app.KeyguardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.PowerManager
import androidx.core.content.ContextCompat
import com.personalassistant.android.auth.SessionManager
import com.personalassistant.android.voice.VoiceSessionController
import com.personalassistant.shared.DefaultWakePhrase
import com.personalassistant.shared.DefaultWakeProfileId
import com.personalassistant.shared.ConnectivityState
import com.personalassistant.shared.VoiceActivationGateway
import com.personalassistant.shared.VoiceActivationRequest
import com.personalassistant.shared.VoiceActivationSource
import com.personalassistant.shared.VoiceUiState
import com.personalassistant.shared.WakeActivationController
import com.personalassistant.shared.WakeActivationPolicy
import com.personalassistant.shared.WakeWordConfig
import com.personalassistant.shared.WakeWordError
import com.personalassistant.shared.WakeWordState
import java.util.UUID
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch

class WakeWordManager(
    private val context: Context,
    private val sessions: SessionManager,
    private val voice: VoiceSessionController,
    private val connectivity: StateFlow<ConnectivityState>,
    private val scope: CoroutineScope,
    detectorFactory: () -> LocalWakeWordDetector = ::UnavailableLocalWakeWordDetector,
) {
    private val preferences = WakePreferences(context)
    private val engine = AndroidWakeWordEngine(
        context = context,
        scope = scope,
        detectorFactory = detectorFactory,
        registeredDeviceId = sessions::registeredDeviceId,
    )
    private val gateway = object : VoiceActivationGateway {
        override fun hasActiveSession(): Boolean = voice.uiState.value !is VoiceUiState.Idle &&
            voice.uiState.value !is VoiceUiState.Failed

        override suspend fun activate(request: VoiceActivationRequest): Boolean {
            if (!hasMicrophonePermission()) return false
            if (connectivity.value != ConnectivityState.ONLINE) return false
            voice.start(request.conversationId, microphonePermissionGranted = true)
            return voice.uiState.value !is VoiceUiState.Failed
        }
    }
    private val controller = WakeActivationController(
        engine = engine,
        voice = gateway,
        store = preferences,
        policy = ::currentPolicy,
        clockMillis = System::currentTimeMillis,
    )
    private val _state = MutableStateFlow(
        if (preferences.enabled) WakeWordState.SUSPENDED else WakeWordState.DISABLED,
    )
    val state: StateFlow<WakeWordState> = _state
    val error: StateFlow<WakeWordError?> = controller.error
    private val _enabled = MutableStateFlow(preferences.enabled)
    val enabled: StateFlow<Boolean> = _enabled
    val displayPhrase: String = DefaultWakePhrase
    private var serviceActive = false
    private var lastVoiceActive = false

    init {
        scope.launch {
            controller.state.collect { state ->
                _state.value = if (
                    state == WakeWordState.DISABLED && preferences.enabled && !serviceActive
                ) WakeWordState.SUSPENDED else state
            }
        }
        scope.launch {
            engine.state.collect { state ->
                if (state == WakeWordState.ERROR && serviceActive) {
                    controller.suspendForPolicy(WakeWordError.MICROPHONE_UNAVAILABLE)
                }
            }
        }
        scope.launch {
            voice.uiState.collect { state ->
                val active = state !is VoiceUiState.Idle && state !is VoiceUiState.Failed
                if (lastVoiceActive && !active && serviceActive && preferences.enabled) {
                    controller.onVoiceSessionEnded()
                }
                lastVoiceActive = active
            }
        }
    }

    /** Called only after the Activity has shown consent and received JIT RECORD_AUDIO. */
    fun enableFromVisibleUi(conversationId: String) {
        require(conversationId.isNotBlank())
        preferences.saveOptIn(conversationId, DefaultWakeProfileId)
        _enabled.value = true
        _state.value = WakeWordState.ENABLING
        val intent = Intent(context, WakeWordForegroundService::class.java).apply {
            action = WakeWordForegroundService.ACTION_ENABLE
        }
        ContextCompat.startForegroundService(context, intent)
    }

    fun disable() {
        preferences.disable()
        _enabled.value = false
        scope.launch { controller.disable() }
        context.stopService(Intent(context, WakeWordForegroundService::class.java))
        _state.value = WakeWordState.DISABLED
    }

    fun activateManual(conversationId: String) {
        scope.launch {
            controller.activateManual(
                VoiceActivationRequest(
                    activationId = "wake:${UUID.randomUUID()}",
                    conversationId = conversationId,
                    source = VoiceActivationSource.MANUAL,
                ),
            )
        }
    }

    internal suspend fun beginForegroundListening(): Boolean {
        serviceActive = true
        val conversationId = preferences.conversationId ?: return false
        return controller.enable(
            conversationId,
            WakeWordConfig(
                profileId = preferences.profileId,
                displayPhrase = DefaultWakePhrase,
                detectorProfileVersion = "untrained-v1",
            ),
        )
    }

    internal fun onServiceDestroyed() {
        serviceActive = false
        scope.launch { controller.onHostStopped() }
        _state.value = when {
            !preferences.enabled -> WakeWordState.DISABLED
            controller.state.value == WakeWordState.ERROR -> WakeWordState.ERROR
            else -> WakeWordState.SUSPENDED
        }
    }

    internal fun suspendForPolicy(error: WakeWordError) {
        scope.launch { controller.suspendForPolicy(error) }
    }

    internal fun resumeAfterPolicyChange() {
        if (serviceActive && preferences.enabled) scope.launch { controller.resume() }
    }

    internal fun hasMicrophonePermission(): Boolean = ContextCompat.checkSelfPermission(
        context,
        Manifest.permission.RECORD_AUDIO,
    ) == PackageManager.PERMISSION_GRANTED

    private suspend fun currentPolicy(): WakeActivationPolicy {
        val powerManager = context.getSystemService(PowerManager::class.java)
        val keyguard = context.getSystemService(KeyguardManager::class.java)
        val thermalRestricted = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q &&
            powerManager.currentThermalStatus >= PowerManager.THERMAL_STATUS_SEVERE
        return WakeActivationPolicy(
            optedIn = preferences.enabled,
            microphonePermissionGranted = hasMicrophonePermission(),
            authenticated = sessions.hasSession() && sessions.accessToken() != null,
            registeredDeviceId = sessions.registeredDeviceId(),
            deviceUnlocked = !keyguard.isDeviceLocked,
            powerRestricted = powerManager.isPowerSaveMode || thermalRestricted,
        )
    }
}
