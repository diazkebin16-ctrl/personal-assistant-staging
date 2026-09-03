package com.personalassistant.android

import com.personalassistant.android.voice.VoiceSessionController
import com.personalassistant.shared.BoundedVoiceBuffer
import com.personalassistant.shared.InvalidVoiceStateTransition
import com.personalassistant.shared.TranscriptKind
import com.personalassistant.shared.VoiceAuthorityBoundary
import com.personalassistant.shared.VoiceAudioFrame
import com.personalassistant.shared.VoiceFrameBytes
import com.personalassistant.shared.VoiceReconnectPolicy
import com.personalassistant.shared.VoiceSessionState
import com.personalassistant.shared.VoiceStateMachine
import com.personalassistant.shared.VoiceTurnIdentity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class VoiceArchitectureTest {
    @Test fun androidTurnIdsAreUniqueAndValid() {
        val first = VoiceSessionController.newTurnId()
        val second = VoiceSessionController.newTurnId()
        assertTrue(VoiceTurnIdentity.isValid(first))
        assertNotEquals(first, second)
    }

    @Test fun partialTranscriptCannotEnterAssistant() {
        assertFalse(VoiceAuthorityBoundary.transcriptMayEnterAssistant(TranscriptKind.PARTIAL))
    }

    @Test fun finalTranscriptMayEnterCertifiedAssistant() {
        assertTrue(VoiceAuthorityBoundary.transcriptMayEnterAssistant(TranscriptKind.FINAL))
    }

    @Test fun spokenTextCannotGrantAndroidOrAssistantPermission() {
        assertFalse(VoiceAuthorityBoundary.voiceMayGrantOsPermission())
        assertFalse(VoiceAuthorityBoundary.voiceMayGrantAssistantPermission())
    }

    @Test fun spokenTextCannotDisableSafeModeOrChangeRisk() {
        assertFalse(VoiceAuthorityBoundary.voiceMayDisableSafeMode())
        assertFalse(VoiceAuthorityBoundary.voiceMayChangeRisk())
    }

    @Test fun spokenConfirmationCannotFabricateEvidence() {
        assertFalse(VoiceAuthorityBoundary.voiceMayFabricateConfirmation())
    }

    @Test fun spokenFinancialActionCannotExecute() {
        assertFalse(VoiceAuthorityBoundary.voiceMayExecuteFinancialAction())
    }

    @Test fun reconnectAttemptsRemainBounded() {
        assertEquals(3, VoiceReconnectPolicy().maxAttempts)
    }

    @Test fun audioBufferRejectsOverflow() {
        val buffer = BoundedVoiceBuffer(capacity = 1)
        val frame = VoiceAudioFrame("android:test-turn", 0, ByteArray(VoiceFrameBytes))
        assertTrue(buffer.offer(frame))
        assertFalse(buffer.offer(frame.copy(sequence = 1)))
    }

    @Test(expected = InvalidVoiceStateTransition::class)
    fun endedSessionCannotRestart() {
        val machine = VoiceStateMachine()
        machine.transition(VoiceSessionState.ENDED)
        machine.transition(VoiceSessionState.CONNECTING)
    }
}
