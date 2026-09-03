package com.personalassistant.android

import android.content.Context
import androidx.room.Room
import androidx.work.WorkManager
import com.personalassistant.android.auth.LogoutCoordinator
import com.personalassistant.android.auth.SessionManager
import com.personalassistant.android.connectivity.ConnectivityMonitor
import com.personalassistant.android.connectivity.ConnectivityCoordinator
import com.personalassistant.android.data.ConversationRepository
import com.personalassistant.android.data.DeviceRepository
import com.personalassistant.android.data.local.AssistantDatabase
import com.personalassistant.android.data.local.LocalContentCipher
import com.personalassistant.android.data.local.MIGRATION_1_2
import com.personalassistant.android.device.AndroidCapabilities
import com.personalassistant.android.device.InstallationIdentityManager
import com.personalassistant.android.security.EncryptedLocalStore
import com.personalassistant.android.sync.OfflineSyncCoordinator
import com.personalassistant.android.work.DeliveryScheduler
import com.personalassistant.android.voice.AndroidAudioInput
import com.personalassistant.android.voice.AndroidAudioOutput
import com.personalassistant.android.voice.OkHttpVoiceTransport
import com.personalassistant.android.voice.VoiceSessionController
import com.personalassistant.android.wake.WakeWordManager
import com.personalassistant.shared.BackendApiClient
import com.personalassistant.shared.SupabaseAuthApi
import com.personalassistant.shared.configuredHttpClient
import io.ktor.client.HttpClient
import io.ktor.client.engine.okhttp.OkHttp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

class AppContainer(context: Context) {
    private val appContext = context.applicationContext
    private val httpClient = configuredHttpClient(HttpClient(OkHttp))
    private val sessionStore = EncryptedLocalStore(appContext, "secure_session", "pa_session_v1")
    private val deviceStore = EncryptedLocalStore(appContext, "secure_device", "pa_device_store_v1")
    private val authApi = SupabaseAuthApi(BuildConfig.SUPABASE_URL, BuildConfig.SUPABASE_ANON_KEY, httpClient)
    private val applicationScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val voiceSocketClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .pingInterval(15, TimeUnit.SECONDS)
        .build()

    val sessions = SessionManager(sessionStore, authApi)
    private val backend = BackendApiClient(
        BuildConfig.BACKEND_BASE_URL,
        httpClient,
        sessions,
        allowLocalCleartext = BuildConfig.ALLOW_LOCAL_CLEARTEXT,
    )
    val installationIdentity = InstallationIdentityManager(deviceStore)
    val capabilities = AndroidCapabilities()
    val devices = DeviceRepository(backend, installationIdentity, capabilities)
    private val connectivityMonitor = ConnectivityMonitor(appContext)
    val connectivity = ConnectivityCoordinator(connectivityMonitor.state, backend, applicationScope)
    val database: AssistantDatabase = Room.databaseBuilder(
        appContext,
        AssistantDatabase::class.java,
        "assistant-cache.db",
    ).addMigrations(MIGRATION_1_2).build()
    private val workManager = WorkManager.getInstance(appContext)
    private val scheduler = DeliveryScheduler(workManager)
    val logout = LogoutCoordinator(sessions, database, workManager)
    val conversations = ConversationRepository(
        backend,
        database,
        LocalContentCipher(),
        scheduler,
        sessions,
        connectivity,
        logout::deviceRevoked,
    )
    val sync = OfflineSyncCoordinator(
        database,
        scheduler,
        sessions,
        connectivity.state,
        applicationScope,
    )
    val voice = VoiceSessionController(
        backend = backend,
        transportFactory = {
            OkHttpVoiceTransport(voiceSocketClient, BuildConfig.ALLOW_LOCAL_CLEARTEXT)
        },
        audioInput = AndroidAudioInput(appContext, applicationScope),
        audioOutput = AndroidAudioOutput(appContext, applicationScope),
        scope = applicationScope,
        onConversationChanged = { conversationId ->
            conversations.refreshMessages(conversationId)
            conversations.refreshConversations()
        },
    )
    val wake = WakeWordManager(
        context = appContext,
        sessions = sessions,
        voice = voice,
        connectivity = connectivity.state,
        scope = applicationScope,
    )
}
