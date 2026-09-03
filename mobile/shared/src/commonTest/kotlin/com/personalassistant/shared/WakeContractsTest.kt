package com.personalassistant.shared

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.descriptors.elementNames
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

private class FakeWakeWordEngine(
    override var profileAvailable: Boolean = true,
) : WakeWordEngine {
    private val mutableState = MutableStateFlow(WakeWordState.DISABLED)
    override val state: StateFlow<WakeWordState> = mutableState
    override val engineVersion = "fake-local-v1"
    var startCount = 0
    var stopCount = 0
    var suspendCount = 0
    var resumeCount = 0
    var failStart = false
    private var callback: (suspend (WakeWordEvent) -> Unit)? = null

    override suspend fun start(config: WakeWordConfig, onEvent: suspend (WakeWordEvent) -> Unit) {
        check(profileAvailable)
        check(!failStart) { "simulated microphone unavailable" }
        startCount += 1
        callback = onEvent
        mutableState.value = WakeWordState.LISTENING
    }

    override suspend fun stop() {
        stopCount += 1
        callback = null
        mutableState.value = WakeWordState.DISABLED
    }

    override suspend fun suspendListening() {
        suspendCount += 1
        mutableState.value = WakeWordState.SUSPENDED
    }

    override suspend fun resume(config: WakeWordConfig, onEvent: suspend (WakeWordEvent) -> Unit) {
        resumeCount += 1
        callback = onEvent
        mutableState.value = WakeWordState.LISTENING
    }

    suspend fun detect(event: WakeWordEvent) = callback?.invoke(event)
    fun crash() { mutableState.value = WakeWordState.ERROR }
}

private class InMemoryWakeStore : WakeActivationStore {
    var record: WakeActivationRecord? = null
    override suspend fun lastAccepted(): WakeActivationRecord? = record
    override suspend fun saveAccepted(record: WakeActivationRecord) { this.record = record }
}

private class FakeVoiceActivationGateway : VoiceActivationGateway {
    var active = false
    var succeed = true
    val requests = mutableListOf<VoiceActivationRequest>()
    override fun hasActiveSession(): Boolean = active
    override suspend fun activate(request: VoiceActivationRequest): Boolean {
        requests += request
        if (succeed) active = true
        return succeed
    }
}

class WakeContractsTest {
    private var now = 10_000L
    private var policy = allowedPolicy()
    private lateinit var engine: FakeWakeWordEngine
    private lateinit var voice: FakeVoiceActivationGateway
    private lateinit var store: InMemoryWakeStore
    private lateinit var controller: WakeActivationController

    private fun createController(profileAvailable: Boolean = true) {
        engine = FakeWakeWordEngine(profileAvailable)
        voice = FakeVoiceActivationGateway()
        store = InMemoryWakeStore()
        controller = WakeActivationController(engine, voice, store, { policy }, { now })
    }

    @Test fun wakeIsDisabledByDefault() {
        createController()
        assertEquals(WakeWordState.DISABLED, controller.state.value)
    }

    @Test fun validWakeStateLifecycleIsExplicit() {
        val machine = WakeWordStateMachine()
        machine.transition(WakeWordState.ENABLING)
        machine.transition(WakeWordState.READY)
        machine.transition(WakeWordState.LISTENING)
        machine.transition(WakeWordState.DETECTED)
        machine.transition(WakeWordState.ACTIVATING)
        assertEquals(WakeWordState.SUSPENDED, machine.transition(WakeWordState.SUSPENDED))
    }

    @Test fun invalidWakeTransitionIsRejected() {
        assertFailsWith<InvalidWakeStateTransition> {
            WakeWordStateMachine().transition(WakeWordState.LISTENING)
        }
    }

    @Test fun explicitOptInIsRequired() = runTest {
        createController()
        policy = allowedPolicy().copy(optedIn = false)
        assertFalse(controller.enable("conversation-1", config()))
        assertEquals(WakeWordError.OPT_IN_REQUIRED, controller.error.value)
    }

    @Test fun microphonePermissionIsIndependentAndRequired() = runTest {
        createController()
        policy = allowedPolicy().copy(microphonePermissionGranted = false)
        assertFalse(controller.enable("conversation-1", config()))
        assertEquals(WakeWordError.MIC_PERMISSION_DENIED, controller.error.value)
        assertFalse(WakeAuthorityBoundary.wakeMayGrantOsPermission())
    }

    @Test fun unavailableModelFailsClosedWithoutStartingEngine() = runTest {
        createController(profileAvailable = false)
        assertFalse(controller.enable("conversation-1", config()))
        assertEquals(WakeWordError.ENGINE_UNAVAILABLE, controller.error.value)
        assertEquals(0, engine.startCount)
    }

    @Test fun simulatedMicrophoneUnavailableFailsClosed() = runTest {
        createController()
        engine.failStart = true
        assertFalse(controller.enable("conversation-1", config()))
        assertEquals(WakeWordError.MICROPHONE_UNAVAILABLE, controller.error.value)
        assertTrue(voice.requests.isEmpty())
    }

    @Test fun fakeEngineSupportsDetectionAndSinglePhase9Handoff() = runTest {
        createController()
        assertTrue(controller.enable("conversation-1", config()))
        val event = event("wake:event-0001")
        engine.detect(event)
        assertEquals(1, voice.requests.size)
        assertEquals(VoiceActivationSource.WAKE_WORD, voice.requests.single().source)
        assertEquals("conversation-1", voice.requests.single().conversationId)
        assertEquals(WakeWordState.ACTIVATING, controller.state.value)
    }

    @Test fun duplicateDetectorCallbackActivatesExactlyOnce() = runTest {
        createController()
        controller.enable("conversation-1", config())
        val event = event("wake:event-0002")
        assertEquals(VoiceActivationOutcome.STARTED, controller.handleWakeEvent(event))
        voice.active = false
        controller.onVoiceSessionEnded()
        assertEquals(VoiceActivationOutcome.DUPLICATE, controller.handleWakeEvent(event))
        assertEquals(1, voice.requests.size)
        assertEquals(1, controller.metrics.value.duplicateCount)
    }

    @Test fun refractoryPeriodDebouncesDifferentCallbacks() = runTest {
        createController()
        controller.enable("conversation-1", config())
        assertEquals(VoiceActivationOutcome.STARTED, controller.handleWakeEvent(event("wake:event-0003")))
        voice.active = false
        controller.onVoiceSessionEnded()
        now += 500
        assertEquals(
            VoiceActivationOutcome.DEBOUNCED,
            controller.handleWakeEvent(event("wake:event-0004", now)),
        )
        assertEquals(1, voice.requests.size)
        assertEquals(1, controller.metrics.value.debouncedCount)
    }

    @Test fun falsePositiveCanOnlyProduceControlledActivationNotAuthority() = runTest {
        createController()
        controller.enable("conversation-1", config())
        engine.detect(event("wake:false-positive-0001"))
        assertEquals(1, voice.requests.size)
        assertFalse(WakeAuthorityBoundary.wakeMayConfirm())
        assertFalse(WakeAuthorityBoundary.wakeMayCallExecutor())
    }

    @Test fun activeVoiceSessionReceivesFocusWithoutSecondSession() = runTest {
        createController()
        controller.enable("conversation-1", config())
        voice.active = true
        assertEquals(
            VoiceActivationOutcome.FOCUSED_EXISTING_SESSION,
            controller.handleWakeEvent(event("wake:event-0005")),
        )
        assertTrue(voice.requests.isEmpty())
    }

    @Test fun deviceMismatchFailsBeforeVoice() = runTest {
        createController()
        controller.enable("conversation-1", config())
        assertEquals(
            VoiceActivationOutcome.DEVICE_MISMATCH,
            controller.handleWakeEvent(event("wake:event-0006", deviceId = "device-other")),
        )
        assertTrue(voice.requests.isEmpty())
    }

    @Test fun lockScreenFailsClosedBeforeVoice() = runTest {
        createController()
        controller.enable("conversation-1", config())
        policy = allowedPolicy().copy(deviceUnlocked = false)
        assertEquals(
            VoiceActivationOutcome.LOCKED,
            controller.handleWakeEvent(event("wake:event-0007")),
        )
        assertTrue(voice.requests.isEmpty())
    }

    @Test fun revokedOrExpiredAuthFailsBeforeVoice() = runTest {
        createController()
        controller.enable("conversation-1", config())
        policy = allowedPolicy().copy(authenticated = false)
        assertEquals(
            VoiceActivationOutcome.AUTH_REQUIRED,
            controller.handleWakeEvent(event("wake:event-0008")),
        )
        assertTrue(voice.requests.isEmpty())
    }

    @Test fun powerRestrictionIsExplicitAndFailClosed() = runTest {
        createController()
        policy = allowedPolicy().copy(powerRestricted = true)
        assertFalse(controller.enable("conversation-1", config()))
        assertEquals(WakeWordError.POWER_RESTRICTED, controller.error.value)
    }

    @Test fun staleAndFutureEventsCannotActivateLaterSession() = runTest {
        createController()
        controller.enable("conversation-1", config())
        assertEquals(
            VoiceActivationOutcome.STALE_EVENT,
            controller.handleWakeEvent(event("wake:event-0009", now - MaxWakeEventAgeMillis - 1)),
        )
        assertEquals(
            VoiceActivationOutcome.STALE_EVENT,
            controller.handleWakeEvent(event("wake:event-0010", now + 1_001)),
        )
        assertTrue(voice.requests.isEmpty())
    }

    @Test fun malformedProfileEventFailsClosed() = runTest {
        createController()
        controller.enable("conversation-1", config())
        assertEquals(
            VoiceActivationOutcome.MALFORMED_EVENT,
            controller.handleWakeEvent(
                event("wake:event-0011").copy(detectorProfileVersion = "other-v1"),
            ),
        )
        assertTrue(voice.requests.isEmpty())
    }

    @Test fun processRecreationUsesDurableActivationIdentity() = runTest {
        createController()
        controller.enable("conversation-1", config())
        val event = event("wake:event-0012")
        controller.handleWakeEvent(event)
        val durableStore = store
        val replacementEngine = FakeWakeWordEngine()
        val replacementVoice = FakeVoiceActivationGateway()
        val replacement = WakeActivationController(
            replacementEngine,
            replacementVoice,
            durableStore,
            { policy },
            { now },
        )
        replacement.enable("conversation-1", config())
        assertEquals(VoiceActivationOutcome.DUPLICATE, replacement.handleWakeEvent(event))
        assertTrue(replacementVoice.requests.isEmpty())
    }

    @Test fun manualAndWakeActivationConvergeOnSameGateway() = runTest {
        createController()
        policy = allowedPolicy().copy(optedIn = false)
        assertEquals(
            VoiceActivationOutcome.STARTED,
            controller.activateManual(
                VoiceActivationRequest(
                    "wake:manual-0001",
                    "conversation-1",
                    VoiceActivationSource.MANUAL,
                ),
            ),
        )
        assertEquals(1, voice.requests.size)
        assertEquals(VoiceActivationSource.MANUAL, voice.requests.single().source)
    }

    @Test fun failedHandoffNeverBecomesSuccess() = runTest {
        createController()
        controller.enable("conversation-1", config())
        voice.succeed = false
        assertEquals(
            VoiceActivationOutcome.FAILED,
            controller.handleWakeEvent(event("wake:event-0013")),
        )
        assertEquals(WakeWordState.SUSPENDED, controller.state.value)
    }

    @Test fun disablingStopsEngineAndIgnoresLateEvents() = runTest {
        createController()
        controller.enable("conversation-1", config())
        val late = event("wake:event-0014")
        controller.disable()
        assertEquals(VoiceActivationOutcome.DISABLED, controller.handleWakeEvent(late))
        assertEquals(1, engine.stopCount)
        assertTrue(voice.requests.isEmpty())
    }

    @Test fun permissionRevocationSuspendsAndClosesCapture() = runTest {
        createController()
        controller.enable("conversation-1", config())
        controller.suspendForPolicy(WakeWordError.MIC_PERMISSION_DENIED)
        assertEquals(WakeWordState.SUSPENDED, controller.state.value)
        assertEquals(1, engine.suspendCount)
    }

    @Test fun engineErrorCanBeSuspendedAndResumedWithoutNewActivation() = runTest {
        createController()
        controller.enable("conversation-1", config())
        engine.crash()
        controller.suspendForPolicy(WakeWordError.MICROPHONE_UNAVAILABLE)
        assertEquals(WakeWordState.SUSPENDED, controller.state.value)
        assertTrue(controller.resume())
        assertEquals(WakeWordState.LISTENING, controller.state.value)
        assertTrue(voice.requests.isEmpty())
        assertEquals(1, controller.metrics.value.detectorRestartCount)
    }

    @Test fun noAuthorityCanBeDerivedFromWake() {
        assertFalse(WakeAuthorityBoundary.wakeMayAuthenticate())
        assertFalse(WakeAuthorityBoundary.wakeMayGrantAssistantPermission())
        assertFalse(WakeAuthorityBoundary.wakeMayConfirm())
        assertFalse(WakeAuthorityBoundary.wakeMayChangeRisk())
        assertFalse(WakeAuthorityBoundary.wakeMayChangeSensitivity())
        assertFalse(WakeAuthorityBoundary.wakeMayDisableSafeMode())
        assertFalse(WakeAuthorityBoundary.wakeMayCallProvider())
        assertFalse(WakeAuthorityBoundary.wakeMayCallExecutor())
        assertFalse(WakeAuthorityBoundary.wakeMayExecuteFinancialAction())
    }

    @Test fun preWakePrivacyBoundaryIsAbsolute() {
        assertFalse(WakeAuthorityBoundary.preWakeAudioMayLeaveDevice())
        assertFalse(WakeAuthorityBoundary.preWakeAudioMayBePersisted())
        assertFalse(WakeAuthorityBoundary.wakePhraseMayBecomeMemory())
    }

    @OptIn(ExperimentalSerializationApi::class)
    @Test fun wakeEventCarriesMetadataOnly() {
        val names = WakeWordEvent.serializer().descriptor.elementNames.toSet()
        assertEquals(
            setOf(
                "event_id",
                "device_id",
                "detected_at_epoch_millis",
                "engine_version",
                "detector_profile_version",
                "confidence_bucket",
            ),
            names,
        )
        assertFalse(names.any { it.contains("audio") || it.contains("transcript") })
    }

    @Test fun wakeConfigurationIsBounded() {
        assertFailsWith<IllegalArgumentException> {
            WakeWordConfig(confidenceThreshold = 0.1f)
        }
        assertFailsWith<IllegalArgumentException> {
            WakeWordConfig(refractoryMillis = 999)
        }
        assertEquals(DefaultWakePhrase, WakeWordConfig().displayPhrase)
    }

    @Test fun boundedPreWakeFrameBudgetIsSmallAndFixed() {
        assertEquals(25, MaxWakePcmFrames)
        assertTrue(AndroidIndependentWakeLimits.maxBufferedMillis() <= 500)
    }

    private fun config() = WakeWordConfig(detectorProfileVersion = "fake-profile-v1")

    private fun event(
        id: String,
        detectedAt: Long = now,
        deviceId: String = "device-registered",
    ) = WakeWordEvent(
        eventId = id,
        deviceId = deviceId,
        detectedAtEpochMillis = detectedAt,
        engineVersion = "fake-local-v1",
        detectorProfileVersion = "fake-profile-v1",
        confidenceBucket = WakeConfidenceBucket.HIGH,
    )

    private fun allowedPolicy() = WakeActivationPolicy(
        optedIn = true,
        microphonePermissionGranted = true,
        authenticated = true,
        registeredDeviceId = "device-registered",
        deviceUnlocked = true,
        powerRestricted = false,
    )
}

private object AndroidIndependentWakeLimits {
    fun maxBufferedMillis(): Int = MaxWakePcmFrames * 20
}
