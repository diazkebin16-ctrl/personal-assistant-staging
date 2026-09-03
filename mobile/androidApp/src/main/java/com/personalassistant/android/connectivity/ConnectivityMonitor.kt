package com.personalassistant.android.connectivity

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import com.personalassistant.shared.ConnectivityState
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.distinctUntilChanged

class ConnectivityMonitor(context: Context) {
    private val manager = context.getSystemService(ConnectivityManager::class.java)

    val state: Flow<ConnectivityState> = callbackFlow {
        fun current(): ConnectivityState {
            val network = manager.activeNetwork ?: return ConnectivityState.OFFLINE
            val capabilities = manager.getNetworkCapabilities(network)
                ?: return ConnectivityState.UNKNOWN
            return if (
                capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
                capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
            ) ConnectivityState.RECOVERING else ConnectivityState.DEGRADED
        }

        trySend(current())
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) { trySend(current()) }
            override fun onLost(network: Network) { trySend(current()) }
            override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) {
                trySend(current())
            }
        }
        manager.registerNetworkCallback(
            NetworkRequest.Builder().addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET).build(),
            callback,
        )
        awaitClose { manager.unregisterNetworkCallback(callback) }
    }.distinctUntilChanged()
}
