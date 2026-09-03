package com.personalassistant.android.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Palette = lightColorScheme(
    primary = Color(0xFF315C55),
    onPrimary = Color.White,
    secondary = Color(0xFF6C5D53),
    background = Color(0xFFFFF8F5),
    surface = Color(0xFFFFF8F5),
    surfaceVariant = Color(0xFFE7EFEA),
    error = Color(0xFFBA1A1A),
)

@Composable
fun PersonalAssistantTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Palette, content = content)
}

