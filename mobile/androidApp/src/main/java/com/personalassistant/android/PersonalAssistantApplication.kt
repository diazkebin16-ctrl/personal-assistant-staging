package com.personalassistant.android

import android.app.Application
import androidx.work.Configuration
import com.personalassistant.android.work.AssistantWorkerFactory
import com.personalassistant.android.work.workerConfiguration

class PersonalAssistantApplication : Application(), Configuration.Provider {
    lateinit var container: AppContainer
        private set

    private val workerFactory by lazy {
        AssistantWorkerFactory { container.conversations }
    }

    override val workManagerConfiguration: Configuration
        get() = workerConfiguration(workerFactory)

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}

