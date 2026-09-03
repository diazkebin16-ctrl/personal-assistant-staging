package com.personalassistant.android.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.personalassistant.android.AppContainer
import com.personalassistant.android.data.ConversationRepository
import com.personalassistant.shared.ApiResult
import com.personalassistant.shared.ConnectivityState
import com.personalassistant.shared.VoiceUiState
import com.personalassistant.shared.WakeWordError
import com.personalassistant.shared.WakeWordState
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class AssistantViewModel(private val container: AppContainer) : ViewModel() {
    private val _sessionState = MutableStateFlow<SessionState>(SessionState.Checking)
    val sessionState: StateFlow<SessionState> = _sessionState
    private val _selectedConversationId = MutableStateFlow<String?>(null)
    private val _notice = MutableStateFlow<UserNotice?>(null)
    val notice: StateFlow<UserNotice?> = _notice
    val voiceState: StateFlow<VoiceUiState> = container.voice.uiState
    val voiceMuted: StateFlow<Boolean> = container.voice.muted
    val wakeState: StateFlow<WakeWordState> = container.wake.state
    val wakeEnabled: StateFlow<Boolean> = container.wake.enabled
    val wakeError: StateFlow<WakeWordError?> = container.wake.error
    val wakePhrase: String = container.wake.displayPhrase

    val connectivity = container.connectivity.state.stateIn(
        viewModelScope,
        SharingStarted.WhileSubscribed(5_000),
        ConnectivityState.UNKNOWN,
    )
    val conversations = container.conversations.conversations().stateIn(
        viewModelScope,
        SharingStarted.WhileSubscribed(5_000),
        emptyList(),
    )
    val pending = container.conversations.pendingOperations().stateIn(
        viewModelScope,
        SharingStarted.WhileSubscribed(5_000),
        emptyList(),
    )

    @OptIn(ExperimentalCoroutinesApi::class)
    val messages = _selectedConversationId.flatMapLatest { id ->
        if (id == null) flowOf(emptyList()) else container.conversations.messages(id)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val selectedConversation = combine(_selectedConversationId, conversations) { id, items ->
        items.firstOrNull { it.id == id }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    init {
        viewModelScope.launch {
            if (container.sessions.hasSession()) authenticateDevice(allowCachedOffline = true)
            else _sessionState.value = SessionState.SignedOut
        }
    }

    fun signIn(email: String, password: String) {
        viewModelScope.launch {
            _sessionState.value = SessionState.Authenticating
            when (val result = container.sessions.signIn(email.trim(), password)) {
                is ApiResult.Success -> authenticateDevice(allowCachedOffline = false)
                is ApiResult.Failure -> _sessionState.value = SessionState.Failed(result.category.name)
            }
        }
    }

    private suspend fun authenticateDevice(allowCachedOffline: Boolean) {
        _sessionState.value = SessionState.RegisteringDevice
        when (val registered = container.devices.register()) {
            is ApiResult.Success -> {
                container.logout.bindAuthenticated(registered.value)
                _sessionState.value = SessionState.Ready
                container.sync.onAuthenticated()
                container.conversations.refreshConversations()
            }
            is ApiResult.Failure -> {
                if (registered.code == "DEVICE_REVOKED") {
                    container.wake.disable()
                    container.voice.end()
                    container.logout.deviceRevoked()
                    _sessionState.value = SessionState.SignedOut
                } else if (registered.category.name == "AUTHENTICATION") {
                    container.wake.disable()
                    container.voice.end()
                    container.logout.authenticationExpired()
                    _sessionState.value = SessionState.SignedOut
                } else if (
                    allowCachedOffline && registered.retryable &&
                    container.sessions.currentAuthorityBinding() != null
                ) {
                    _sessionState.value = SessionState.Ready
                    _notice.value = UserNotice.OfflineSession
                } else {
                    _sessionState.value = SessionState.Failed(registered.code ?: registered.category.name)
                }
            }
        }
    }

    fun createConversation() {
        viewModelScope.launch {
            when (val result = container.conversations.createConversation(null)) {
                is ApiResult.Success -> _selectedConversationId.value = result.value.id
                is ApiResult.Failure -> _notice.value = UserNotice.Error(result.category.name, result.retryable)
            }
        }
    }

    fun openConversation(id: String) {
        _selectedConversationId.value = id
        viewModelScope.launch { container.conversations.refreshMessages(id) }
    }

    fun closeConversation() { _selectedConversationId.value = null }

    fun send(content: String) {
        val conversation = selectedConversation.value ?: return
        if (content.isBlank()) return
        viewModelScope.launch {
            when (
                container.conversations.enqueueMessage(
                    conversation.id,
                    content.trim(),
                    conversation.version,
                )
            ) {
                is ConversationRepository.EnqueueResult.Queued ->
                    _notice.value = if (connectivity.value == ConnectivityState.ONLINE) null
                    else UserNotice.QueuedOffline
                ConversationRepository.EnqueueResult.AuthenticationRequired ->
                    _notice.value = UserNotice.Error("AUTH_REQUIRED", false)
                ConversationRepository.EnqueueResult.QueueFull ->
                    _notice.value = UserNotice.Error("OFFLINE_QUEUE_FULL", false)
                ConversationRepository.EnqueueResult.InvalidRequest ->
                    _notice.value = UserNotice.Error("INVALID_MESSAGE", false)
                ConversationRepository.EnqueueResult.LocalStorageFailure ->
                    _notice.value = UserNotice.Error("LOCAL_STORAGE_UNAVAILABLE", false)
            }
        }
    }

    fun retry(operationId: String) {
        viewModelScope.launch {
            when (container.conversations.retryDelivery(operationId)) {
                ConversationRepository.RetryScheduleResult.Scheduled ->
                    _notice.value = UserNotice.QueuedOffline
                ConversationRepository.RetryScheduleResult.NotFound ->
                    _notice.value = UserNotice.Error("MESSAGE_NOT_FOUND", false)
                ConversationRepository.RetryScheduleResult.AuthenticationRequired ->
                    _notice.value = UserNotice.Error("AUTH_REQUIRED", false)
                ConversationRepository.RetryScheduleResult.IdentityMismatch ->
                    _notice.value = UserNotice.Error("IDENTITY_BINDING_MISMATCH", false)
                ConversationRepository.RetryScheduleResult.Terminal ->
                    _notice.value = UserNotice.Error("MESSAGE_FAILED", false)
            }
        }
    }

    fun cancel(operationId: String) {
        viewModelScope.launch {
            _notice.value = when (container.conversations.cancel(operationId)) {
                ConversationRepository.CancellationResult.CancelledLocally -> UserNotice.CancelledLocally
                ConversationRepository.CancellationResult.ServerResultPending -> UserNotice.CancellationPending
                ConversationRepository.CancellationResult.NotFound -> UserNotice.Error("MESSAGE_NOT_FOUND", false)
                ConversationRepository.CancellationResult.AuthenticationRequired -> UserNotice.Error("AUTH_REQUIRED", false)
                ConversationRepository.CancellationResult.IdentityMismatch -> UserNotice.Error("IDENTITY_BINDING_MISMATCH", false)
                ConversationRepository.CancellationResult.AlreadyTerminal -> UserNotice.Error("MESSAGE_ALREADY_TERMINAL", false)
            }
        }
    }

    fun confirm(confirmationId: String) {
        viewModelScope.launch {
            when (val result = container.conversations.approveConfirmation(confirmationId)) {
                is ApiResult.Success -> _notice.value = UserNotice.ConfirmationRecorded
                is ApiResult.Failure -> _notice.value = UserNotice.Error(result.code ?: result.category.name, result.retryable)
            }
        }
    }

    fun startVoice(microphonePermissionGranted: Boolean) {
        val conversation = selectedConversation.value ?: return
        if (!microphonePermissionGranted) {
            _notice.value = UserNotice.Error("MIC_PERMISSION_DENIED", false)
            return
        }
        if (connectivity.value != ConnectivityState.ONLINE) {
            _notice.value = UserNotice.VoiceUnavailableOffline
            return
        }
        container.wake.activateManual(conversation.id)
    }

    fun enableWake(microphonePermissionGranted: Boolean) {
        val conversation = selectedConversation.value ?: return
        if (!microphonePermissionGranted) {
            _notice.value = UserNotice.Error("MIC_PERMISSION_DENIED", false)
            return
        }
        container.wake.enableFromVisibleUi(conversation.id)
    }

    fun disableWake() = container.wake.disable()

    fun endVoice() = container.voice.end()

    fun toggleVoiceMute() = container.voice.toggleMute()

    fun interruptVoice() = container.voice.interruptAssistant()

    fun logout() {
        viewModelScope.launch {
            container.wake.disable()
            container.voice.end()
            container.logout.logout()
            _selectedConversationId.value = null
            _sessionState.value = SessionState.SignedOut
        }
    }

    sealed interface SessionState {
        data object Checking : SessionState
        data object SignedOut : SessionState
        data object Authenticating : SessionState
        data object RegisteringDevice : SessionState
        data object Ready : SessionState
        data class Failed(val code: String) : SessionState
    }

    sealed interface UserNotice {
        data object QueuedOffline : UserNotice
        data object OfflineSession : UserNotice
        data object CancelledLocally : UserNotice
        data object CancellationPending : UserNotice
        data object VoiceUnavailableOffline : UserNotice
        data object ConfirmationRecorded : UserNotice
        data class Error(val code: String, val retryable: Boolean) : UserNotice
    }

    class Factory(private val container: AppContainer) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = AssistantViewModel(container) as T
    }
}
