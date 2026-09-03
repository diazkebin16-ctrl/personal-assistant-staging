package com.personalassistant.android.work

import android.content.Context
import androidx.work.ListenableWorker
import androidx.work.WorkerFactory
import androidx.work.WorkerParameters
import com.personalassistant.android.data.ConversationRepository

class AssistantWorkerFactory(
    private val repository: () -> ConversationRepository,
) : WorkerFactory() {
    override fun createWorker(
        appContext: Context,
        workerClassName: String,
        workerParameters: WorkerParameters,
    ): ListenableWorker? = when (workerClassName) {
        MessageDeliveryWorker::class.java.name ->
            MessageDeliveryWorker(appContext, workerParameters, repository())
        else -> null
    }
}

