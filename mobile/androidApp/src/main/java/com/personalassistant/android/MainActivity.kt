package com.personalassistant.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.personalassistant.android.ui.PersonalAssistantApp
import com.personalassistant.android.ui.theme.PersonalAssistantTheme

class MainActivity : ComponentActivity() {
    private val container: AppContainer
        get() = (application as PersonalAssistantApplication).container

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            PersonalAssistantTheme { PersonalAssistantApp(container) }
        }
    }

    override fun onStop() {
        if (!isChangingConfigurations) container.voice.onAppBackgrounded()
        super.onStop()
    }
}
