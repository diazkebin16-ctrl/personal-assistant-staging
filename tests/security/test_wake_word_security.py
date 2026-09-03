"""Phase 10 privacy, Android-policy, and authority-boundary review tests."""

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
ANDROID = ROOT / "mobile/androidApp"
SHARED = ROOT / "mobile/shared"
WAKE_ANDROID = ANDROID / "src/main/java/com/personalassistant/android/wake"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def wake_android_source() -> str:
    return "\n".join(read(path) for path in WAKE_ANDROID.rglob("*.kt"))


def all_mobile_source() -> str:
    return "\n".join(
        read(path)
        for path in (ROOT / "mobile").rglob("*")
        if path.is_file()
        and "build" not in path.parts
        and ".gradle" not in path.parts
        and path.suffix in {".kt", ".kts", ".xml", ".toml"}
    )


def test_wake_is_default_disabled_and_requires_explicit_visible_ui_opt_in() -> None:
    preferences = read(WAKE_ANDROID / "WakePreferences.kt")
    manager = read(WAKE_ANDROID / "WakeWordManager.kt")
    ui = read(ANDROID / "src/main/java/com/personalassistant/android/ui/PersonalAssistantApp.kt")
    assert "getBoolean(ENABLED, false)" in preferences
    assert "enableFromVisibleUi" in manager
    assert "showWakeConsent" in ui
    assert "Entiendo y activar" in ui


def test_record_audio_is_jit_and_cannot_be_fabricated() -> None:
    ui = read(ANDROID / "src/main/java/com/personalassistant/android/ui/PersonalAssistantApp.kt")
    manager = read(WAKE_ANDROID / "WakeWordManager.kt")
    assert "RequestMultiplePermissions" in ui
    assert "Manifest.permission.RECORD_AUDIO" in ui
    assert "checkSelfPermission" in manager
    assert "PackageManager.PERMISSION_GRANTED" in manager


@pytest.mark.parametrize(
    "authority",
    [
        "wakeMayAuthenticate",
        "wakeMayGrantOsPermission",
        "wakeMayGrantAssistantPermission",
        "wakeMayConfirm",
        "wakeMayChangeRisk",
        "wakeMayChangeSensitivity",
        "wakeMayDisableSafeMode",
        "wakeMayCallProvider",
        "wakeMayCallExecutor",
        "wakeMayExecuteFinancialAction",
    ],
)
def test_wake_has_zero_authority(authority: str) -> None:
    contracts = read(SHARED / "src/commonMain/kotlin/com/personalassistant/shared/WakeContracts.kt")
    assert f"fun {authority}(): Boolean = false" in contracts


def test_pre_wake_audio_is_local_memory_only_and_not_persisted() -> None:
    source = wake_android_source()
    preferences = read(WAKE_ANDROID / "WakePreferences.kt").casefold()
    assert "BackendApiClient" not in source
    assert "OkHttp" not in source
    assert "WebSocket" not in source
    assert "FileOutputStream" not in source
    assert "MediaRecorder(" not in source
    assert "audio" not in preferences


def test_no_ambient_transcription_or_cloud_recognizer_exists() -> None:
    source = wake_android_source()
    assert "SpeechRecognizer" not in source
    assert "RecognitionListener" not in source
    assert "val transcript" not in source.casefold()
    assert "ambientTranscript" not in source


def test_wake_event_schema_contains_no_audio_or_transcript() -> None:
    contracts = read(SHARED / "src/commonMain/kotlin/com/personalassistant/shared/WakeContracts.kt")
    event = contracts.split("data class WakeWordEvent(", 1)[1].split(") {", 1)[0]
    assert "eventId" in event and "deviceId" in event
    assert "audio" not in event.casefold()
    assert "transcript" not in event.casefold()


def test_replay_is_persisted_before_phase9_handoff() -> None:
    contracts = read(SHARED / "src/commonMain/kotlin/com/personalassistant/shared/WakeContracts.kt")
    body = contracts.split("private suspend fun activate(", 1)[1]
    assert body.index("store.saveAccepted") < body.index("voice.activate(request)")


def test_debounce_stale_event_and_device_binding_are_enforced() -> None:
    contracts = read(SHARED / "src/commonMain/kotlin/com/personalassistant/shared/WakeContracts.kt")
    assert "config.refractoryMillis" in contracts
    assert "MaxWakeEventAgeMillis" in contracts
    assert "expectedDeviceId != policy.registeredDeviceId" in contracts


def test_authentication_and_registered_device_are_checked_at_activation_time() -> None:
    manager = read(WAKE_ANDROID / "WakeWordManager.kt")
    assert "sessions.hasSession()" in manager
    assert "sessions.accessToken()" in manager
    assert "sessions.registeredDeviceId()" in manager


def test_lock_screen_and_power_restrictions_fail_closed() -> None:
    manager = read(WAKE_ANDROID / "WakeWordManager.kt")
    service = read(WAKE_ANDROID / "WakeWordForegroundService.kt")
    assert "isDeviceLocked" in manager
    assert "isPowerSaveMode" in manager
    assert "THERMAL_STATUS_SEVERE" in manager
    assert "Intent.ACTION_SCREEN_OFF" in service
    assert "WakeWordError.LOCKED" in service


def test_permission_revocation_is_event_driven_and_suspends_detector() -> None:
    service = read(WAKE_ANDROID / "WakeWordForegroundService.kt")
    assert "AppOpsManager.OnOpChangedListener" in service
    assert "AppOpsManager.OPSTR_RECORD_AUDIO" in service
    assert "startWatchingMode" in service
    assert "stopWatchingMode" in service
    assert "MIC_PERMISSION_DENIED" in service
    assert "suspendForPolicy" in service


def test_activation_identity_is_durable_before_voice_handoff_without_main_thread_io() -> None:
    preferences = read(WAKE_ANDROID / "WakePreferences.kt")
    contracts = read(SHARED / "src/commonMain/kotlin/com/personalassistant/shared/WakeContracts.kt")
    assert "withContext(Dispatchers.IO)" in preferences
    assert ".commit()" in preferences
    assert "check(persisted)" in preferences
    assert contracts.index("store.saveAccepted") < contracts.index("voice.activate")


def test_process_death_and_reboot_do_not_secretly_restart_microphone() -> None:
    service = read(WAKE_ANDROID / "WakeWordForegroundService.kt")
    manifest = read(ANDROID / "src/main/AndroidManifest.xml")
    assert "START_NOT_STICKY" in service
    assert "BOOT_COMPLETED" not in manifest
    assert "RECEIVE_BOOT_COMPLETED" not in manifest
    assert "BroadcastReceiver" not in manifest


def test_user_visible_notification_cannot_be_hidden() -> None:
    service = read(WAKE_ANDROID / "WakeWordForegroundService.kt")
    assert "startForeground(" in service
    assert "Activación por voz disponible" in service
    assert ".setOngoing(true)" in service
    assert "stopForeground(STOP_FOREGROUND_REMOVE)" in service


def test_service_is_user_initiated_and_not_exported() -> None:
    manager = read(WAKE_ANDROID / "WakeWordManager.kt")
    manifest = read(ANDROID / "src/main/AndroidManifest.xml")
    assert "enableFromVisibleUi" in manager
    assert "ContextCompat.startForegroundService" in manager
    declaration = manifest.split('android:name=".wake.WakeWordForegroundService"', 1)[1]
    assert 'android:exported="false"' in declaration


def test_capture_has_fixed_blocking_frames_and_no_busy_loop_or_wake_lock() -> None:
    engine = read(WAKE_ANDROID / "AndroidWakeWordEngine.kt")
    source = wake_android_source()
    assert "FRAME_SAMPLES = 320" in engine
    assert "AudioRecord.READ_BLOCKING" in engine
    assert "delay(" not in engine
    assert "WakeLock" not in source
    assert ".acquire(" not in source


def test_pre_wake_engine_never_takes_audio_focus_or_forces_bluetooth_route() -> None:
    source = wake_android_source()
    assert "requestAudioFocus" not in source
    assert "startBluetoothSco" not in source
    assert "setCommunicationDevice" not in source


def test_detector_failure_closes_audio_record() -> None:
    engine = read(WAKE_ANDROID / "AndroidWakeWordEngine.kt")
    assert "finally" in engine
    assert "localRecorder.release()" in engine
    assert "stopCapture" in engine


def test_no_default_assistant_or_voice_interaction_role_is_claimed() -> None:
    manifest = read(ANDROID / "src/main/AndroidManifest.xml")
    source = wake_android_source()
    assert "VoiceInteractionService" not in source
    assert "android.service.voice.VoiceInteractionService" not in manifest
    assert "ROLE_ASSISTANT" not in source


def test_no_unapproved_background_or_accessibility_bypass() -> None:
    source = all_mobile_source()
    for forbidden in (
        "REQUEST_IGNORE_BATTERY_OPTIMIZATIONS",
        "SYSTEM_ALERT_WINDOW",
        "BIND_ACCESSIBILITY_SERVICE",
        "ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS",
    ):
        assert forbidden not in source


def test_release_detector_has_no_vendor_key_or_secret() -> None:
    source = all_mobile_source()
    for forbidden in (
        "PORCUPINE_ACCESS_KEY",
        "OPENAI_API_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "WAKE_MODEL_SECRET",
    ):
        assert forbidden not in source


def test_release_network_security_is_unchanged_and_tls_strict() -> None:
    manifest = read(ANDROID / "src/main/AndroidManifest.xml")
    config = read(ANDROID / "src/main/res/xml/network_security_config.xml")
    assert 'android:usesCleartextTraffic="false"' in manifest
    assert 'cleartextTrafficPermitted="false"' in config
    assert '<certificates src="system"' in config
    assert 'src="user"' not in config


def test_disabled_detector_ignores_events_and_late_event_is_bounded_in_tests() -> None:
    tests = read(SHARED / "src/commonTest/kotlin/com/personalassistant/shared/WakeContractsTest.kt")
    assert "disablingStopsEngineAndIgnoresLateEvents" in tests
    assert "staleAndFutureEventsCannotActivateLaterSession" in tests


def test_phase9_barge_in_reconnect_and_transcript_boundaries_remain_present() -> None:
    controller = read(
        ANDROID / "src/main/java/com/personalassistant/android/voice/VoiceSessionController.kt"
    )
    contracts = read(
        SHARED / "src/commonMain/kotlin/com/personalassistant/shared/VoiceContracts.kt"
    )
    assert "interruptAssistant" in controller
    assert "VoiceSessionState.RECONNECTING" in controller
    assert "TranscriptKind.PARTIAL" in controller
    assert "transcriptMayEnterAssistant" in contracts


def test_wake_phrase_is_not_interpreted_as_confirmation_or_memory() -> None:
    contracts = read(SHARED / "src/commonMain/kotlin/com/personalassistant/shared/WakeContracts.kt")
    assert "wakeMayConfirm(): Boolean = false" in contracts
    assert "wakePhraseMayBecomeMemory(): Boolean = false" in contracts


def test_default_phrase_avoids_competing_assistant_trademarks() -> None:
    contracts = read(
        SHARED / "src/commonMain/kotlin/com/personalassistant/shared/WakeContracts.kt"
    ).casefold()
    line = next(line for line in contracts.splitlines() if "defaultwakephrase" in line)
    for prohibited in ("hey siri", "alexa", "hey google", "ok google"):
        assert prohibited not in line


def test_no_phase11_offline_system_or_external_executor_was_added() -> None:
    names = {path.name.casefold() for path in ROOT.rglob("*") if path.is_file()}
    assert "offlinesystem.kt" not in names
    assert "executor.kt" not in names
    assert "wakeexecutor.kt" not in names
