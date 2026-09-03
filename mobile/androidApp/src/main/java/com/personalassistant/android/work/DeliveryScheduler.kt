package com.personalassistant.android.work

import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.await
import androidx.work.workDataOf
import com.personalassistant.android.auth.LogoutCoordinator
import java.util.concurrent.TimeUnit

class DeliveryScheduler(private val workManager: WorkManager) {
    suspend fun schedule(operationId: String) {
        val request = OneTimeWorkRequestBuilder<MessageDeliveryWorker>()
            .setInputData(workDataOf(MessageDeliveryWorker.OPERATION_ID to operationId))
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .addTag(LogoutCoordinator.USER_WORK_TAG)
            .build()
        workManager
            .enqueueUniqueWork(uniqueWorkName(operationId), ExistingWorkPolicy.KEEP, request)
            .await()
    }

    suspend fun cancel(operationId: String) {
        workManager.cancelUniqueWork(uniqueWorkName(operationId)).await()
    }

    companion object {
        internal fun uniqueWorkName(operationId: String): String = "message:$operationId"
    }
}
