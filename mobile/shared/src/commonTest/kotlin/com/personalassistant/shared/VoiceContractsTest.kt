package com.personalassistant.shared

import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.descriptors.elementNames
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class VoiceContractsTest {
    @Test fun validVoiceLifecycleTransitionsAreExplicit() {
        val machine = VoiceStateMachine()
        machine.transition(VoiceSessionState.CONNECTING)
        machine.transition(VoiceSessionState.LISTENING)
        machine.transition(VoiceSessionState.PROCESSING)
        machine.transition(VoiceSessionState.SPEAKING)
        machine.transition(VoiceSessionState.INTERRUPTING)
        assertEquals(VoiceSessionState.LISTENING, machine.transition(VoiceSessionState.LISTENING))
    }

    @Test fun invalidVoiceTransitionIsRejected() {
        assertFailsWith<InvalidVoiceStateTransition> {
            VoiceStateMachine().transition(VoiceSessionState.SPEAKING)
        }
    }

    @Test fun terminalVoiceSessionCannotRevive() {
        val machine = VoiceStateMachine()
        machine.transition(VoiceSessionState.ENDED)
        assertFailsWith<InvalidVoiceStateTransition> {
            machine.transition(VoiceSessionState.CONNECTING)
        }
    }

    @Test fun audioBufferIsBoundedAndNeverGrowsPastCapacity() {
        val buffer = BoundedVoiceBuffer(capacity = 2)
        assertTrue(buffer.offer(frame(0)))
        assertTrue(buffer.offer(frame(1)))
        assertFalse(buffer.offer(frame(2)))
        assertEquals(2, buffer.size)
    }

    @Test fun audioBufferPreservesOrdering() {
        val buffer = BoundedVoiceBuffer(capacity = 2)
        buffer.offer(frame(0))
        buffer.offer(frame(1))
        assertEquals(0, buffer.poll()?.sequence)
        assertEquals(1, buffer.poll()?.sequence)
        assertNull(buffer.poll())
    }

    @Test fun audioBufferCanBeClearedOnCancellation() {
        val buffer = BoundedVoiceBuffer()
        buffer.offer(frame(0))
        buffer.clear()
        assertEquals(0, buffer.size)
    }

    @Test fun reconnectIsBoundedToThreeAttempts() {
        assertFailsWith<IllegalArgumentException> { VoiceReconnectPolicy(maxAttempts = 4) }
        assertEquals(3, VoiceReconnectPolicy().maxAttempts)
    }

    @Test fun reconnectBackoffIsBounded() {
        val policy = VoiceReconnectPolicy(maxAttempts = 3, baseDelayMillis = 500, maxDelayMillis = 1_500)
        assertEquals(listOf(500L, 1_000L, 1_500L), (1..3).map(policy::delayMillis))
    }

    @Test fun partialTranscriptCannotEnterAssistantPipeline() {
        assertFalse(VoiceAuthorityBoundary.transcriptMayEnterAssistant(TranscriptKind.PARTIAL))
        assertTrue(VoiceAuthorityBoundary.transcriptMayEnterAssistant(TranscriptKind.FINAL))
    }

    @Test fun partialTranscriptCannotWriteMemoryCreateTaskOrConfirm() {
        assertFalse(VoiceAuthorityBoundary.partialMayWriteMemory())
        assertFalse(VoiceAuthorityBoundary.partialMayCreateTask())
        assertFalse(VoiceAuthorityBoundary.partialMayConfirm())
    }

    @Test fun voiceCannotGrantEitherPermissionLayer() {
        assertFalse(VoiceAuthorityBoundary.voiceMayGrantAssistantPermission())
        assertFalse(VoiceAuthorityBoundary.voiceMayGrantOsPermission())
    }

    @Test fun voiceCannotChangeRiskOrSafeMode() {
        assertFalse(VoiceAuthorityBoundary.voiceMayChangeRisk())
        assertFalse(VoiceAuthorityBoundary.voiceMayDisableSafeMode())
    }

    @Test fun voiceCannotFabricateConfirmationOrExecuteFinance() {
        assertFalse(VoiceAuthorityBoundary.voiceMayFabricateConfirmation())
        assertFalse(VoiceAuthorityBoundary.voiceMayExecuteFinancialAction())
    }

    @OptIn(ExperimentalSerializationApi::class)
    @Test fun sessionRequestCannotForceOwnerModelProviderOrSensitivity() {
        val names = VoiceSessionCreateRequest.serializer().descriptor.elementNames.toSet()
        assertFalse("user_id" in names)
        assertFalse("device_id" in names)
        assertFalse("provider" in names)
        assertFalse("model" in names)
        assertFalse("sensitivity" in names)
        assertFalse("voice_profile" in names)
    }

    @Test fun voiceStreamUrlUsesWssAndRejectsArbitraryPaths() {
        val api = testApi("https://backend.example")
        assertEquals(
            "wss://backend.example/api/v1/voice/sessions/s/stream",
            api.voiceStreamUrl("/api/v1/voice/sessions/s/stream"),
        )
        assertFailsWith<IllegalArgumentException> { api.voiceStreamUrl("/execute-anything") }
        assertFailsWith<IllegalArgumentException> {
            api.voiceStreamUrl("/api/v1/voice/../execute")
        }
    }

    private fun frame(sequence: Int) = VoiceAudioFrame(
        turnId = "voice:test-turn",
        sequence = sequence,
        bytes = ByteArray(VoiceFrameBytes),
    )

    private fun testApi(baseUrl: String) = BackendApiClient(
        baseUrl,
        io.ktor.client.HttpClient(io.ktor.client.engine.mock.MockEngine { error("unused") }),
        object : SessionHeadersProvider {
            override suspend fun accessToken(): String? = null
            override suspend fun registeredDeviceId(): String? = null
        },
    )
}
