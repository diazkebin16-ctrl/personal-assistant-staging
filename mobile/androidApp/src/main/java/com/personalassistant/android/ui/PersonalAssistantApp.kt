package com.personalassistant.android.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.core.content.ContextCompat
import com.personalassistant.android.AppContainer
import com.personalassistant.android.data.ConversationRepository
import com.personalassistant.android.data.local.ConversationEntity
import com.personalassistant.android.data.local.PendingOperationEntity
import com.personalassistant.shared.ConnectivityState
import com.personalassistant.shared.OfflineOperationState
import com.personalassistant.shared.VoiceUiState
import com.personalassistant.shared.WakeWordError
import com.personalassistant.shared.WakeWordState

@Composable
fun PersonalAssistantApp(container: AppContainer) {
    val model: AssistantViewModel = viewModel(factory = AssistantViewModel.Factory(container))
    val session by model.sessionState.collectAsStateWithLifecycle()
    when (session) {
        AssistantViewModel.SessionState.SignedOut -> LoginScreen(model::signIn)
        AssistantViewModel.SessionState.Ready -> AssistantHome(model)
        is AssistantViewModel.SessionState.Failed -> FailureScreen((session as AssistantViewModel.SessionState.Failed).code, model::logout)
        else -> LoadingScreen(if (session is AssistantViewModel.SessionState.RegisteringDevice) "Securing this device…" else "Signing in…")
    }
}

@Composable
private fun LoginScreen(signIn: (String, String) -> Unit) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    Column(
        modifier = Modifier.fillMaxSize().padding(28.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Your assistant", style = MaterialTheme.typography.headlineLarge)
        Text("One identity, securely available on this device.", color = MaterialTheme.colorScheme.secondary)
        Spacer(Modifier.height(28.dp))
        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Email") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            singleLine = true,
        )
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Password") },
            visualTransformation = PasswordVisualTransformation(),
            singleLine = true,
        )
        Spacer(Modifier.height(20.dp))
        Button(
            onClick = { signIn(email, password) },
            modifier = Modifier.fillMaxWidth(),
            enabled = email.isNotBlank() && password.isNotBlank(),
        ) { Text("Sign in") }
    }
}

@Composable
private fun AssistantHome(model: AssistantViewModel) {
    val selected by model.selectedConversation.collectAsStateWithLifecycle()
    if (selected == null) ConversationListScreen(model) else ChatScreen(model, selected!!)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ConversationListScreen(model: AssistantViewModel) {
    val conversations by model.conversations.collectAsStateWithLifecycle()
    val connectivity by model.connectivity.collectAsStateWithLifecycle()
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Conversations") },
                actions = { TextButton(onClick = model::logout) { Text("Sign out") } },
            )
        },
        floatingActionButton = { Button(onClick = model::createConversation) { Text("New conversation") } },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            ConnectivityBanner(connectivity)
            if (conversations.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("Start a conversation with your assistant.")
                }
            } else {
                LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
                    items(conversations, key = { it.id }) { conversation ->
                        Card(
                            onClick = { model.openConversation(conversation.id) },
                            modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
                        ) {
                            Column(Modifier.padding(18.dp)) {
                                Text(conversation.title ?: "Conversation", style = MaterialTheme.typography.titleMedium)
                                Text("Updated ${conversation.updatedAt.take(16).replace('T', ' ')}", style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ChatScreen(model: AssistantViewModel, conversation: ConversationEntity) {
    val messages by model.messages.collectAsStateWithLifecycle()
    val pending by model.pending.collectAsStateWithLifecycle()
    val notice by model.notice.collectAsStateWithLifecycle()
    val connectivity by model.connectivity.collectAsStateWithLifecycle()
    val voiceState by model.voiceState.collectAsStateWithLifecycle()
    val voiceMuted by model.voiceMuted.collectAsStateWithLifecycle()
    val wakeState by model.wakeState.collectAsStateWithLifecycle()
    val wakeEnabled by model.wakeEnabled.collectAsStateWithLifecycle()
    val wakeError by model.wakeError.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val microphonePermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted -> model.startVoice(granted) }
    val wakePermissions = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { grants -> model.enableWake(grants[Manifest.permission.RECORD_AUDIO] == true) }
    var showWakeConsent by remember { mutableStateOf(false) }
    var draft by remember { mutableStateOf("") }
    val conversationPending = pending.filter { it.conversationId == conversation.id }

    Scaffold(topBar = {
        TopAppBar(
            title = { Text(conversation.title ?: "Your assistant") },
            navigationIcon = { TextButton(onClick = model::closeConversation) { Text("Back") } },
        )
    }) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            ConnectivityBanner(connectivity)
            NoticeBanner(notice)
            VoicePanel(
                state = voiceState,
                muted = voiceMuted,
                start = {
                    val granted = ContextCompat.checkSelfPermission(
                        context,
                        Manifest.permission.RECORD_AUDIO,
                    ) == PackageManager.PERMISSION_GRANTED
                    if (granted) model.startVoice(true)
                    else microphonePermission.launch(Manifest.permission.RECORD_AUDIO)
                },
                end = model::endVoice,
                mute = model::toggleVoiceMute,
                interrupt = model::interruptVoice,
            )
            WakeWordPanel(
                enabled = wakeEnabled,
                state = wakeState,
                error = wakeError,
                phrase = model.wakePhrase,
                enable = { showWakeConsent = true },
                disable = model::disableWake,
            )
            LazyColumn(
                modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 14.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                itemsIndexed(messages, key = { _, item -> item.id }) { _, message -> MessageBubble(message, model::confirm) }
                items(conversationPending, key = { it.operationId }) { operation ->
                    PendingBubble(operation, model::retry, model::cancel)
                }
            }
            Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.Bottom) {
                OutlinedTextField(
                    value = draft,
                    onValueChange = { draft = it },
                    modifier = Modifier.weight(1f),
                    placeholder = { Text("Message your assistant") },
                    maxLines = 5,
                )
                Button(
                    onClick = { model.send(draft); draft = "" },
                    enabled = draft.isNotBlank(),
                    modifier = Modifier.padding(start = 8.dp),
                ) { Text("Send") }
            }
        }
    }
    if (showWakeConsent) {
        AlertDialog(
            onDismissRequest = { showWakeConsent = false },
            title = { Text("Activar por voz") },
            text = {
                Text(
                    "El detector escucha localmente mientras la notificación está visible. " +
                        "El audio anterior a la activación no se envía ni se guarda. " +
                        "Después de detectar la frase comienza la sesión de voz segura. " +
                        "Puedes desactivarlo en cualquier momento.",
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    showWakeConsent = false
                    val permissions = buildList {
                        add(Manifest.permission.RECORD_AUDIO)
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                            add(Manifest.permission.POST_NOTIFICATIONS)
                        }
                    }.toTypedArray()
                    val audioGranted = ContextCompat.checkSelfPermission(
                        context,
                        Manifest.permission.RECORD_AUDIO,
                    ) == PackageManager.PERMISSION_GRANTED
                    if (audioGranted) model.enableWake(true) else wakePermissions.launch(permissions)
                }) { Text("Entiendo y activar") }
            },
            dismissButton = {
                TextButton(onClick = { showWakeConsent = false }) { Text("Cancelar") }
            },
        )
    }
}

@Composable
private fun WakeWordPanel(
    enabled: Boolean,
    state: WakeWordState,
    error: WakeWordError?,
    phrase: String,
    enable: () -> Unit,
    disable: () -> Unit,
) {
    val status = when (state) {
        WakeWordState.DISABLED -> "Activación por voz desactivada"
        WakeWordState.ENABLING, WakeWordState.READY -> "Preparando activación por voz…"
        WakeWordState.LISTENING -> "Escuchando localmente…"
        WakeWordState.DETECTED, WakeWordState.ACTIVATING -> "Iniciando conversación…"
        WakeWordState.SUSPENDED -> when (error) {
            WakeWordError.ENGINE_UNAVAILABLE -> "El perfil local requiere un modelo aprobado."
            WakeWordError.MIC_PERMISSION_DENIED -> "Activación pausada: falta permiso de micrófono."
            WakeWordError.LOCKED -> "Activación pausada mientras el teléfono está bloqueado."
            WakeWordError.POWER_RESTRICTED -> "Activación pausada por energía o temperatura."
            else -> "Activación por voz pausada"
        }
        WakeWordState.ERROR -> when (error) {
            WakeWordError.ENGINE_UNAVAILABLE -> "El perfil local requiere un modelo aprobado."
            WakeWordError.MIC_PERMISSION_DENIED -> "El micrófono requiere tu permiso."
            WakeWordError.LOCKED -> "Desbloquea el teléfono para activar por voz."
            WakeWordError.POWER_RESTRICTED -> "Activación pausada por energía o temperatura."
            else -> "Micrófono no disponible"
        }
    }
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(Modifier.fillMaxWidth().padding(12.dp)) {
            Text("Wake Word", style = MaterialTheme.typography.titleSmall)
            Text(status, style = MaterialTheme.typography.labelLarge)
            Text("Frase: “$phrase”", style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = if (enabled) disable else enable) {
                Text(if (enabled) "Desactivar" else "Activar")
            }
        }
    }
}

@Composable
private fun VoicePanel(
    state: VoiceUiState,
    muted: Boolean,
    start: () -> Unit,
    end: () -> Unit,
    mute: () -> Unit,
    interrupt: () -> Unit,
) {
    val label = when (state) {
        VoiceUiState.Idle -> "Voice is ready when you are."
        VoiceUiState.Connecting -> "Conectando…"
        is VoiceUiState.Listening -> state.partialTranscript?.let { "Escuchando… $it" }
            ?: "Escuchando…"
        VoiceUiState.Processing -> "Pensando…"
        VoiceUiState.Speaking -> "Hablando…"
        VoiceUiState.Interrupting -> "Interrumpiendo…"
        is VoiceUiState.Reconnecting -> "Reconectando… (${state.attempt}/3)"
        is VoiceUiState.WaitingConfirmation -> "Necesito tu confirmación…"
        is VoiceUiState.WaitingPermission -> "Necesito tu permiso para continuar…"
        is VoiceUiState.Unavailable -> "No puedo completar eso…"
        is VoiceUiState.Failed -> when (state.error) {
            com.personalassistant.shared.VoiceErrorCode.NETWORK_UNAVAILABLE -> "Sin conexión…"
            com.personalassistant.shared.VoiceErrorCode.MIC_PERMISSION_DENIED ->
                "El micrófono requiere tu permiso."
            else -> "No puedo completar eso…"
        }
    }
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(Modifier.fillMaxWidth().padding(12.dp)) {
            Text(label, style = MaterialTheme.typography.labelLarge)
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                when (state) {
                    VoiceUiState.Idle, is VoiceUiState.Failed ->
                        TextButton(onClick = start) { Text("Start voice") }
                    else -> {
                        TextButton(onClick = end) { Text("Return to text") }
                        TextButton(onClick = mute) { Text(if (muted) "Unmute" else "Mute") }
                        if (state is VoiceUiState.Speaking) {
                            TextButton(onClick = interrupt) { Text("Interrupt") }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MessageBubble(message: ConversationRepository.CachedMessage, confirm: (String) -> Unit) {
    val fromUser = message.role == "USER"
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (fromUser) Arrangement.End else Arrangement.Start) {
        Card(
            modifier = Modifier.widthIn(max = 340.dp),
            colors = CardDefaults.cardColors(
                containerColor = if (fromUser) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant,
                contentColor = if (fromUser) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
            ),
        ) {
            Column(Modifier.padding(14.dp)) {
                Text(message.content)
                if (message.isStale) {
                    Text(
                        if (message.sensitiveContentHidden) "Sensitive cache hidden"
                        else "Cached server state — may be stale",
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
                when (message.outcome) {
                    "ACTION_WAITING_CONFIRMATION", "MEMORY_CONFIRMATION_REQUIRED" -> {
                        Text("Your confirmation is required.", style = MaterialTheme.typography.labelMedium)
                        message.confirmationRequestId?.let { id ->
                            TextButton(onClick = { confirm(id) }) { Text("Confirm securely") }
                        }
                    }
                    "ACTION_WAITING_PERMISSION", "MEMORY_PERMISSION_REQUIRED" ->
                        Text("Permission is required before this can continue.", style = MaterialTheme.typography.labelMedium)
                    "ACTION_READY_FOR_FUTURE_EXECUTION" ->
                        Text("Prepared, but no executor is available. Nothing was performed.", style = MaterialTheme.typography.labelMedium)
                    "ACTION_UNSUPPORTED" -> Text("This action is unavailable.", style = MaterialTheme.typography.labelMedium)
                    "ACTION_DENIED" -> Text("This action was not authorized.", style = MaterialTheme.typography.labelMedium)
                }
            }
        }
    }
}

@Composable
private fun PendingBubble(
    operation: PendingOperationEntity,
    retry: (String) -> Unit,
    cancel: (String) -> Unit,
) {
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Row(Modifier.padding(12.dp).fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                when (operation.status) {
                    OfflineOperationState.PENDING.name -> "Saved locally — pending delivery"
                    OfflineOperationState.WAITING_FOR_NETWORK.name -> "Waiting for a secure connection"
                    OfflineOperationState.SYNCING.name -> "Synchronizing…"
                    OfflineOperationState.ACKNOWLEDGED.name -> "Accepted by the server"
                    OfflineOperationState.RETRYABLE_FAILURE.name -> "Temporary delivery failure"
                    OfflineOperationState.AUTH_REQUIRED.name -> "Sign-in required to continue"
                    OfflineOperationState.REJECTED.name -> "Rejected by the server"
                    OfflineOperationState.CANCEL_REQUESTED.name -> "Cancellation requested — server result unknown"
                    OfflineOperationState.CANCELLED.name -> "Cancelled before server acceptance"
                    else -> "Message was not delivered"
                },
                modifier = Modifier.weight(1f),
            )
            if (
                operation.status in setOf(
                    OfflineOperationState.RETRYABLE_FAILURE.name,
                    OfflineOperationState.AUTH_REQUIRED.name,
                ) && operation.attemptCount < ConversationRepository.MAX_ATTEMPTS
            ) {
                TextButton(onClick = { retry(operation.operationId) }) { Text("Retry") }
            }
            if (
                operation.status in setOf(
                    OfflineOperationState.PENDING.name,
                    OfflineOperationState.WAITING_FOR_NETWORK.name,
                    OfflineOperationState.RETRYABLE_FAILURE.name,
                    OfflineOperationState.AUTH_REQUIRED.name,
                    OfflineOperationState.SYNCING.name,
                )
            ) {
                TextButton(onClick = { cancel(operation.operationId) }) { Text("Cancel") }
            }
        }
    }
}

@Composable
private fun ConnectivityBanner(state: ConnectivityState) {
    if (state == ConnectivityState.ONLINE) return
    val message = when (state) {
        ConnectivityState.OFFLINE -> "Offline — messages will wait safely"
        ConnectivityState.DEGRADED -> "Degraded — the backend is not reliably available"
        ConnectivityState.RECOVERING -> "Connection restored — verifying the backend"
        ConnectivityState.UNKNOWN -> "Connection status unknown"
        ConnectivityState.ONLINE -> return
    }
    Text(
        message,
        modifier = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant).padding(8.dp),
        style = MaterialTheme.typography.labelMedium,
    )
}

@Composable
private fun NoticeBanner(notice: AssistantViewModel.UserNotice?) {
    val text = when (notice) {
        AssistantViewModel.UserNotice.QueuedOffline -> "Message queued for delivery."
        AssistantViewModel.UserNotice.OfflineSession -> "Using cached data offline. Server authority will be revalidated."
        AssistantViewModel.UserNotice.CancelledLocally -> "Pending message cancelled locally before server acceptance."
        AssistantViewModel.UserNotice.CancellationPending -> "Cancellation requested. The server result is still unknown."
        AssistantViewModel.UserNotice.VoiceUnavailableOffline -> "Realtime voice is unavailable until the backend connection is verified."
        AssistantViewModel.UserNotice.ConfirmationRecorded -> "Confirmation recorded by the server. The action has not been executed."
        is AssistantViewModel.UserNotice.Error -> if (notice.retryable) "Temporary failure. Retry is available." else "The request could not be completed (${notice.code})."
        null -> return
    }
    Text(text, Modifier.fillMaxWidth().padding(8.dp), style = MaterialTheme.typography.labelMedium)
}

@Composable
private fun LoadingScreen(label: String) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            CircularProgressIndicator()
            Spacer(Modifier.height(12.dp))
            Text(label)
        }
    }
}

@Composable
private fun FailureScreen(code: String, signOut: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(28.dp), verticalArrangement = Arrangement.Center) {
        Text("Connection unavailable", style = MaterialTheme.typography.headlineMedium)
        Text("The assistant failed safely. No action was authorized. ($code)")
        Spacer(Modifier.height(16.dp))
        Button(onClick = signOut) { Text("Return to sign in") }
    }
}
