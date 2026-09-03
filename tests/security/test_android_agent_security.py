"""Static security assertions for boundaries that must be reviewable without an emulator."""

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
MOBILE = ROOT / "mobile"
ANDROID = MOBILE / "androidApp"
SHARED = MOBILE / "shared"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def all_mobile_source() -> str:
    return "\n".join(
        read(path)
        for path in MOBILE.rglob("*")
        if path.is_file()
        and "build" not in path.parts
        and ".gradle" not in path.parts
        and path.suffix in {".kt", ".kts", ".xml", ".toml"}
    )


def test_installation_identity_is_cryptographically_random_and_app_scoped() -> None:
    source = read(
        ANDROID
        / "src/main/java/com/personalassistant/android/device/InstallationIdentityManager.kt"
    )
    assert "SecureRandom" in source
    assert "ByteArray(24)" in source
    assert '"android:"' in source


@pytest.mark.parametrize(
    "prohibited",
    [
        "TelephonyManager",
        "getImei",
        "getMeid",
        "WifiInfo",
        "getMacAddress",
        "ADVERTISING_ID",
        "Build.SERIAL",
        "Settings.Secure.ANDROID_ID",
    ],
)
def test_device_identity_avoids_hardware_and_tracking_identifiers(prohibited: str) -> None:
    source = read(
        ANDROID
        / "src/main/java/com/personalassistant/android/device/InstallationIdentityManager.kt"
    )
    assert prohibited not in source


def test_private_device_key_is_non_exportable_keystore_material() -> None:
    source = read(
        ANDROID
        / "src/main/java/com/personalassistant/android/device/InstallationIdentityManager.kt"
    )
    assert '"AndroidKeyStore"' in source
    assert "getCertificate" in source
    assert "privateKey" not in source


def test_session_material_uses_authenticated_keystore_encryption() -> None:
    source = read(
        ANDROID / "src/main/java/com/personalassistant/android/security/AndroidKeystoreCipher.kt"
    )
    assert "AES/GCM/NoPadding" in source
    assert "setRandomizedEncryptionRequired(true)" in source
    assert "GCMParameterSpec(128" in source


def test_logout_clears_session_cache_and_authenticated_work() -> None:
    source = read(ANDROID / "src/main/java/com/personalassistant/android/auth/LogoutCoordinator.kt")
    assert "cancelAllWorkByTag" in source
    assert "clearAllTables" in source
    assert "sessionManager.logout" in source


def test_android_declares_only_network_and_jit_voice_permissions() -> None:
    manifest = read(ANDROID / "src/main/AndroidManifest.xml")
    requested = [
        block
        for block in manifest.split("<uses-permission")[1:]
        if 'tools:node="remove"' not in block.split("/>", 1)[0]
    ]
    assert len(requested) == 6
    assert "android.permission.INTERNET" in requested[0]
    assert "android.permission.ACCESS_NETWORK_STATE" in requested[1]
    assert "android.permission.RECORD_AUDIO" in requested[2]
    assert "android.permission.POST_NOTIFICATIONS" in requested[3]
    assert "android.permission.FOREGROUND_SERVICE" in requested[4]
    assert "android.permission.FOREGROUND_SERVICE_MICROPHONE" in requested[5]


@pytest.mark.parametrize(
    "permission",
    [
        "CAMERA",
        "ACCESS_FINE_LOCATION",
        "READ_CONTACTS",
        "READ_CALENDAR",
        "WRITE_CALENDAR",
        "READ_SMS",
        "CALL_PHONE",
        "BIND_ACCESSIBILITY_SERVICE",
    ],
)
def test_no_invasive_permission_is_requested(permission: str) -> None:
    assert permission not in read(ANDROID / "src/main/AndroidManifest.xml")


def test_microphone_permission_is_requested_only_from_explicit_voice_ui() -> None:
    ui = read(ANDROID / "src/main/java/com/personalassistant/android/ui/PersonalAssistantApp.kt")
    controller = read(
        ANDROID / "src/main/java/com/personalassistant/android/voice/VoiceSessionController.kt"
    )
    application = read(
        ANDROID / "src/main/java/com/personalassistant/android/PersonalAssistantApplication.kt"
    )
    assert "rememberLauncherForActivityResult" in ui
    assert "RequestPermission" in ui
    assert "Start voice" in ui
    assert "requestPermissions" not in controller
    assert "RECORD_AUDIO" not in application


def test_production_manifest_denies_cleartext_and_backup() -> None:
    manifest = read(ANDROID / "src/main/AndroidManifest.xml")
    assert 'android:usesCleartextTraffic="false"' in manifest
    assert 'android:allowBackup="false"' in manifest


def test_release_network_trusts_system_cas_only() -> None:
    config = read(ANDROID / "src/main/res/xml/network_security_config.xml")
    assert 'cleartextTrafficPermitted="false"' in config
    assert '<certificates src="system"' in config
    assert 'src="user"' not in config


def test_debug_cleartext_is_scoped_to_local_emulator_hosts() -> None:
    config = read(ANDROID / "src/debug/res/xml/network_security_config_debug.xml")
    assert "10.0.2.2" in config
    assert "localhost" in config
    assert "production" not in config


def test_production_build_disables_local_cleartext_transport() -> None:
    build = read(ANDROID / "build.gradle.kts")
    production = build.split('create("production")', 1)[1].split("buildTypes", 1)[0]
    assert 'buildConfigField("Boolean", "ALLOW_LOCAL_CLEARTEXT", "false")' in production


@pytest.mark.parametrize(
    "bypass", ["trustAll", "X509TrustManager", "HostnameVerifier", "sslSocketFactory", "proceed()"]
)
def test_no_tls_validation_bypass(bypass: str) -> None:
    assert bypass not in all_mobile_source()


def test_no_raw_http_logging_plugin_is_installed() -> None:
    source = read(SHARED / "src/commonMain/kotlin/com/personalassistant/shared/Network.kt")
    assert "install(Logging)" not in source
    assert "LogLevel" not in source


@pytest.mark.parametrize(
    "secret_name",
    [
        "SUPABASE_SERVICE_ROLE_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "BACKEND_SECRET",
        "PRIVATE KEY-----",
    ],
)
def test_no_server_or_provider_secret_is_embedded(secret_name: str) -> None:
    assert secret_name not in all_mobile_source()


def test_client_request_has_no_owner_or_routing_authority_fields() -> None:
    contracts = read(SHARED / "src/commonMain/kotlin/com/personalassistant/shared/Contracts.kt")
    request = contracts.split("data class AssistantRequest", 1)[1].split(")", 1)[0]
    assert "userId" not in request
    assert "model" not in request
    assert "provider" not in request
    assert "sensitivity" not in request


def test_capability_layers_are_independent() -> None:
    source = read(
        SHARED / "src/commonMain/kotlin/com/personalassistant/shared/SecuritySemantics.kt"
    )
    for field in (
        "deviceSupports",
        "osPermissionGranted",
        "assistantPermissionGranted",
        "actionAuthorized",
    ):
        assert field in source
    assert (
        "deviceSupports && osPermissionGranted && assistantPermissionGranted && actionAuthorized"
        in source
    )


def test_model_text_cannot_create_authority() -> None:
    source = read(
        SHARED / "src/commonMain/kotlin/com/personalassistant/shared/SecuritySemantics.kt"
    )
    assert "modelTextGrantsAuthority" in source
    assert "= false" in source


def test_client_exposes_no_general_executor() -> None:
    source = read(
        SHARED / "src/commonMain/kotlin/com/personalassistant/shared/SecuritySemantics.kt"
    )
    assert "canExecuteExternalAction" in source
    assert "= false" in source


def test_financial_actions_are_explicitly_prohibited() -> None:
    source = read(
        SHARED / "src/commonMain/kotlin/com/personalassistant/shared/SecuritySemantics.kt"
    )
    for action in (
        "buy",
        "sell",
        "transfer",
        "withdraw",
        "deposit",
        "place_order",
        "change_leverage",
        "increase_risk",
    ):
        assert f'"{action}"' in source


def test_no_direct_task_or_memory_mutation_endpoint() -> None:
    source = read(SHARED / "src/commonMain/kotlin/com/personalassistant/shared/Network.kt")
    assert '"/api/v1/tasks' not in source
    assert '"/api/v1/memories' not in source
    assert "AuthorizedActionEnvelope" not in source


def test_confirmation_uses_server_authority_endpoint() -> None:
    source = read(SHARED / "src/commonMain/kotlin/com/personalassistant/shared/Network.kt")
    assert "/api/v1/confirmations/$confirmationId/approve" in source


def test_truthful_pending_states_are_not_completed() -> None:
    source = read(
        SHARED / "src/commonMain/kotlin/com/personalassistant/shared/SecuritySemantics.kt"
    )
    assert "ACTION_WAITING_CONFIRMATION" in source and "WaitingConfirmation" in source
    assert "ACTION_WAITING_PERMISSION" in source and "WaitingPermission" in source
    assert "ACTION_READY_FOR_FUTURE_EXECUTION" in source and "ReadyButExecutorUnavailable" in source


def test_idempotency_is_stored_with_pending_operation() -> None:
    entity = read(ANDROID / "src/main/java/com/personalassistant/android/data/local/Entities.kt")
    repository = read(
        ANDROID / "src/main/java/com/personalassistant/android/data/ConversationRepository.kt"
    )
    assert 'Index(value = ["idempotencyKey"], unique = true)' in entity
    assert "idempotencyKey = claimedOperation.idempotencyKey" in repository


def test_work_is_unique_bounded_and_backed_off() -> None:
    scheduler = read(
        ANDROID / "src/main/java/com/personalassistant/android/work/DeliveryScheduler.kt"
    )
    worker = read(
        ANDROID / "src/main/java/com/personalassistant/android/work/MessageDeliveryWorker.kt"
    )
    assert "enqueueUniqueWork" in scheduler
    assert "ExistingWorkPolicy.KEEP" in scheduler
    assert "BackoffPolicy.EXPONENTIAL" in scheduler
    assert "MAX_ATTEMPTS" in worker


def test_no_periodic_or_foreground_work() -> None:
    source = all_mobile_source()
    assert "PeriodicWorkRequest" not in source
    kotlin_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in MOBILE.rglob("*.kt")
        if "/build/" not in str(path)
    )
    assert "setForeground" not in kotlin_source
    manifest = read(ANDROID / "src/main/AndroidManifest.xml")
    foreground_declaration = manifest.split("SystemForegroundService", 1)[1].split("/>", 1)[0]
    assert 'tools:node="remove"' in foreground_declaration
    assert "setForeground" not in source


def test_local_release_variant_is_disabled() -> None:
    build = read(ANDROID / "build.gradle.kts")
    assert 'withBuildType("release")' in build
    assert 'it.second == "local"' in build
    assert "variant.enable = false" in build


def test_production_and_staging_urls_require_https() -> None:
    build = read(ANDROID / "build.gradle.kts")
    assert 'require(value.startsWith("https://"))' in build
    assert "productionBackendUrl" in build
    assert "stagingBackendUrl" in build


def test_exported_components_are_minimized_and_no_deep_link_exists() -> None:
    manifest = read(ANDROID / "src/main/AndroidManifest.xml")
    assert manifest.count('android:exported="true"') == 1
    assert "android.intent.category.BROWSABLE" not in manifest
    for tag in ("<service", "<receiver"):
        for declaration in manifest.split(tag)[1:]:
            block = declaration.split("/>", 1)[0]
            assert 'tools:node="remove"' in block or 'android:exported="false"' in block
    assert "androidx.work.WorkManagerInitializer" in manifest
    assert 'tools:node="remove"' in manifest
