package com.personalassistant.android.wake

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.app.AppOpsManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.IBinder
import android.os.Build
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.annotation.RequiresApi
import com.personalassistant.android.MainActivity
import com.personalassistant.android.PersonalAssistantApplication
import com.personalassistant.android.R
import com.personalassistant.shared.WakeWordError
import com.personalassistant.shared.WakeWordState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch

class WakeWordForegroundService : Service() {
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val manager: WakeWordManager
        get() = (application as PersonalAssistantApplication).container.wake
    private val powerManager by lazy { getSystemService(PowerManager::class.java) }
    private val appOpsManager by lazy { getSystemService(AppOpsManager::class.java) }
    private var foregroundStarted = false

    private val policyReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                Intent.ACTION_SCREEN_OFF -> manager.suspendForPolicy(WakeWordError.LOCKED)
                Intent.ACTION_USER_PRESENT -> manager.resumeAfterPolicyChange()
                PowerManager.ACTION_POWER_SAVE_MODE_CHANGED -> {
                    if (powerManager.isPowerSaveMode) {
                        manager.suspendForPolicy(WakeWordError.POWER_RESTRICTED)
                    } else {
                        manager.resumeAfterPolicyChange()
                    }
                }
            }
        }
    }

    private val microphoneOpListener = AppOpsManager.OnOpChangedListener { op, changedPackage ->
        if (
            op == AppOpsManager.OPSTR_RECORD_AUDIO &&
            changedPackage == packageName &&
            !manager.hasMicrophonePermission()
        ) {
            manager.suspendForPolicy(WakeWordError.MIC_PERMISSION_DENIED)
        }
    }
    private var thermalListener: Any? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        val filter = IntentFilter().apply {
            addAction(Intent.ACTION_SCREEN_OFF)
            addAction(Intent.ACTION_USER_PRESENT)
            addAction(PowerManager.ACTION_POWER_SAVE_MODE_CHANGED)
        }
        ContextCompat.registerReceiver(
            this,
            policyReceiver,
            filter,
            ContextCompat.RECEIVER_NOT_EXPORTED,
        )
        appOpsManager.startWatchingMode(
            AppOpsManager.OPSTR_RECORD_AUDIO,
            packageName,
            microphoneOpListener,
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            registerThermalListener()
        }
        serviceScope.launch {
            manager.state.collect { state ->
                if (foregroundStarted) {
                    startForeground(
                        NOTIFICATION_ID,
                        buildNotification(notificationStatus(state)),
                    )
                }
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action != ACTION_ENABLE || !manager.hasMicrophonePermission()) {
            stopSelf(startId)
            return START_NOT_STICKY
        }
        foregroundStarted = true
        startForeground(NOTIFICATION_ID, buildNotification("Preparando activación por voz…"))
        serviceScope.launch {
            if (!manager.beginForegroundListening()) {
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf(startId)
            }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        foregroundStarted = false
        appOpsManager.stopWatchingMode(microphoneOpListener)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            unregisterThermalListener()
        }
        runCatching { unregisterReceiver(policyReceiver) }
        manager.onServiceDestroyed()
        serviceScope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    @RequiresApi(Build.VERSION_CODES.Q)
    private fun registerThermalListener() {
        val listener = PowerManager.OnThermalStatusChangedListener { status ->
            if (status >= PowerManager.THERMAL_STATUS_SEVERE) {
                manager.suspendForPolicy(WakeWordError.POWER_RESTRICTED)
            } else {
                manager.resumeAfterPolicyChange()
            }
        }
        thermalListener = listener
        powerManager.addThermalStatusListener(mainExecutor, listener)
    }

    @RequiresApi(Build.VERSION_CODES.Q)
    private fun unregisterThermalListener() {
        (thermalListener as? PowerManager.OnThermalStatusChangedListener)?.let { listener ->
            powerManager.removeThermalStatusListener(listener)
        }
        thermalListener = null
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Activación por voz",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Muestra cuándo el detector local de activación puede usar el micrófono"
            setSound(null, null)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun buildNotification(status: String) = NotificationCompat.Builder(this, CHANNEL_ID)
        .setSmallIcon(R.drawable.ic_launcher_foreground)
        .setContentTitle("Activación por voz disponible")
        .setContentText(status)
        .setOngoing(true)
        .setOnlyAlertOnce(true)
        .setContentIntent(
            PendingIntent.getActivity(
                this,
                0,
                Intent(this, MainActivity::class.java),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            ),
        )
        .build()

    private fun notificationStatus(state: WakeWordState): String = when (state) {
        WakeWordState.ENABLING, WakeWordState.READY -> "Preparando activación por voz…"
        WakeWordState.LISTENING -> "Escuchando localmente…"
        WakeWordState.DETECTED, WakeWordState.ACTIVATING -> "Conversación por voz activa"
        WakeWordState.SUSPENDED -> "Activación por voz pausada"
        WakeWordState.ERROR -> "Activación por voz no disponible"
        WakeWordState.DISABLED -> "Activación por voz desactivada"
    }

    companion object {
        const val ACTION_ENABLE = "com.personalassistant.android.wake.ENABLE"
        private const val CHANNEL_ID = "wake_activation"
        private const val NOTIFICATION_ID = 1010
    }
}
