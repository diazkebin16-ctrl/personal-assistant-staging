package com.personalassistant.android

import com.personalassistant.shared.DefaultWakePhrase
import com.personalassistant.shared.InvalidWakeStateTransition
import com.personalassistant.shared.MaxWakeEventAgeMillis
import com.personalassistant.shared.MaxWakePcmFrames
import com.personalassistant.shared.WakeActivationIdentity
import com.personalassistant.shared.WakeAuthorityBoundary
import com.personalassistant.shared.WakeWordConfig
import com.personalassistant.shared.WakeWordState
import com.personalassistant.shared.WakeWordStateMachine
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WakeWordArchitectureTest {
    @Test fun wakeStartsDisabled() = assertEquals(
        WakeWordState.DISABLED,
        WakeWordStateMachine().state,
    )

    @Test(expected = InvalidWakeStateTransition::class)
    fun detectorCannotJumpFromDisabledToListening() {
        WakeWordStateMachine().transition(WakeWordState.LISTENING)
    }

    @Test fun wakeActivationIdentityIsStrictlyNamespaced() {
        assertTrue(WakeActivationIdentity.isValid("wake:android-event-0001"))
        assertFalse(WakeActivationIdentity.isValid("voice:android-event-0001"))
    }

    @Test fun neutralPhraseIsNotAnotherAssistantBrand() {
        assertEquals("Hola asistente", DefaultWakePhrase)
        val normalized = DefaultWakePhrase.lowercase()
        for (brand in listOf("siri", "alexa", "google")) assertFalse(brand in normalized)
    }

    @Test fun debounceAndEventAgeAreBounded() {
        val config = WakeWordConfig()
        assertTrue(config.refractoryMillis in 1_000L..10_000L)
        assertEquals(5_000L, MaxWakeEventAgeMillis)
    }

    @Test fun preWakeBufferBudgetIsBounded() = assertTrue(MaxWakePcmFrames <= 25)

    @Test fun wakeCannotAuthenticate() = assertFalse(WakeAuthorityBoundary.wakeMayAuthenticate())
    @Test fun wakeCannotConfirm() = assertFalse(WakeAuthorityBoundary.wakeMayConfirm())
    @Test fun wakeCannotGrantOsPermission() =
        assertFalse(WakeAuthorityBoundary.wakeMayGrantOsPermission())
    @Test fun wakeCannotGrantAssistantPermission() =
        assertFalse(WakeAuthorityBoundary.wakeMayGrantAssistantPermission())
    @Test fun wakeCannotChangeRiskOrSensitivity() {
        assertFalse(WakeAuthorityBoundary.wakeMayChangeRisk())
        assertFalse(WakeAuthorityBoundary.wakeMayChangeSensitivity())
    }
    @Test fun wakeCannotDisableSafeMode() =
        assertFalse(WakeAuthorityBoundary.wakeMayDisableSafeMode())
    @Test fun wakeCannotCallProviderOrExecutor() {
        assertFalse(WakeAuthorityBoundary.wakeMayCallProvider())
        assertFalse(WakeAuthorityBoundary.wakeMayCallExecutor())
    }
    @Test fun wakeCannotExecuteFinance() =
        assertFalse(WakeAuthorityBoundary.wakeMayExecuteFinancialAction())
    @Test fun preWakeAudioCannotLeaveDeviceOrPersist() {
        assertFalse(WakeAuthorityBoundary.preWakeAudioMayLeaveDevice())
        assertFalse(WakeAuthorityBoundary.preWakeAudioMayBePersisted())
    }
}
