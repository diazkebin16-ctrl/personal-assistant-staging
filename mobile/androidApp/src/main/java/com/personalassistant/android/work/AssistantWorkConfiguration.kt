package com.personalassistant.android.work

import androidx.work.Configuration

fun workerConfiguration(factory: AssistantWorkerFactory): Configuration =
    Configuration.Builder()
        .setWorkerFactory(factory)
        .setMinimumLoggingLevel(android.util.Log.WARN)
        .build()

