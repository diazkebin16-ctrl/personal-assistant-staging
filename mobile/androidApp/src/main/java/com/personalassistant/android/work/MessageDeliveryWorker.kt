package com.personalassistant.android.work

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.personalassistant.android.data.ConversationRepository

class MessageDeliveryWorker(
    appContext: Context,
    parameters: WorkerParameters,
    private val repository: ConversationRepository,
) : CoroutineWorker(appContext, parameters) {
    override suspend fun doWork(): Result {
        if (runAttemptCount >= ConversationRepository.MAX_ATTEMPTS) return Result.failure()
        val operationId = inputData.getString(OPERATION_ID) ?: return Result.failure()
        return when (repository.deliver(operationId)) {
            ConversationRepository.DeliveryResult.Success -> Result.success()
            ConversationRepository.DeliveryResult.Retry -> Result.retry()
            ConversationRepository.DeliveryResult.AuthenticationRequired -> Result.failure()
            ConversationRepository.DeliveryResult.NoWork -> Result.success()
            ConversationRepository.DeliveryResult.TerminalFailure -> Result.failure()
        }
    }

    companion object { const val OPERATION_ID = "operation_id" }
}
