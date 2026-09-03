package com.personalassistant.android.connectivity

import com.personalassistant.shared.ApiResult
import com.personalassistant.shared.BackendApiClient
import com.personalassistant.shared.ConnectivityState
import com.personalassistant.shared.ErrorCategory
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

/**
 * Combines validated link events with a backend liveness probe. A network interface alone never
 * means ONLINE, and authentication failures do not incorrectly mean OFFLINE.
 */
class ConnectivityCoordinator(
    linkStates: Flow<ConnectivityState>,
    private val backend: BackendApiClient,
    scope: CoroutineScope,
) {
    private val _state = MutableStateFlow(ConnectivityState.UNKNOWN)
    val state: StateFlow<ConnectivityState> = _state.asStateFlow()
    @Volatile private var lastLinkState: ConnectivityState = ConnectivityState.UNKNOWN

    init {
        scope.launch {
            linkStates.collectLatest { linkState ->
                lastLinkState = linkState
                when (linkState) {
                    ConnectivityState.OFFLINE -> _state.value = ConnectivityState.OFFLINE
                    ConnectivityState.UNKNOWN -> _state.value = ConnectivityState.UNKNOWN
                    ConnectivityState.DEGRADED -> _state.value = ConnectivityState.DEGRADED
                    ConnectivityState.RECOVERING,
                    ConnectivityState.ONLINE,
                    -> {
                        _state.value = ConnectivityState.RECOVERING
                        when (val probe = backend.health()) {
                            is ApiResult.Success -> _state.value = ConnectivityState.ONLINE
                            is ApiResult.Failure -> reportBackendFailure(probe.category)
                        }
                    }
                }
            }
        }
    }

    fun reportBackendSuccess() {
        if (lastLinkState != ConnectivityState.OFFLINE) _state.value = ConnectivityState.ONLINE
    }

    fun reportBackendFailure(category: ErrorCategory) {
        _state.value = when {
            lastLinkState == ConnectivityState.OFFLINE -> ConnectivityState.OFFLINE
            category in setOf(
                ErrorCategory.NETWORK_UNAVAILABLE,
                ErrorCategory.TIMEOUT,
                ErrorCategory.SERVER_UNAVAILABLE,
            ) -> ConnectivityState.DEGRADED
            else -> ConnectivityState.ONLINE // Backend responded; this is an authority/auth error.
        }
    }
}
