"""Phase 10 Android/KMP structural contract and immutable-history checks."""

import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
MOBILE = ROOT / "mobile"
ANDROID = MOBILE / "androidApp"
SHARED = MOBILE / "shared"

HISTORICAL_MIGRATIONS = {
    "0001_identity_auth.py": "5a1509b3dd29827fc4e28a317a30d1f30d5f3d34aad6c21fd4933a47d70406d3",
    "0002_permissions_risk_audit.py": (
        "97d5cdf542fcb4d3fd431da91d369b97aa6d9b393b2c4fa56da22d984c269cb1"
    ),
    "0003_capability_actions.py": (
        "1ab2551bdf07efe50b703826d938b77872829c131c24e893103ab60d02c1b475"
    ),
    "0004_task_engine.py": "06b33700da8cf2cb9fc9c19db21ad196a824d7806798af2a6d207d3851b4d224",
    "0005_memory_core.py": "e7f78a9287b9a336dd959a7c2345fa992feb24df2dcb1286425dce85da390c6a",
    "0006_ai_router.py": "2ec3d7773df3bd0fe4b9f6488cbf9bd67bbe5eb0897fc3e5758f3bc047130538",
    "0007_orchestrator.py": "6a410084439c5f84baae9774ce5223824d0f148ee504f80a1583612f5a1f016d",
    "0008_text_assistant.py": "2e8edbd5bf9e3e474375d74c79e5f5d0e70931824d73a0d9133f090524a0d337",
    "0009_realtime_voice.py": "5f8da86ac7fa46f48ca417176a782e0ff3ad41fc800b49952777ae8574cbbea9",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(("filename", "expected"), HISTORICAL_MIGRATIONS.items())
def test_certified_migrations_remain_byte_identical(filename: str, expected: str) -> None:
    payload = (ROOT / "backend/migrations/versions" / filename).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == expected


def test_phase10_has_no_migration() -> None:
    assert not (ROOT / "backend/migrations/versions/0010_wake_word.py").exists()
    versions = list((ROOT / "backend/migrations/versions").glob("*.py"))
    assert (ROOT / "backend/migrations/versions/0010_web_research.py").is_file()
    assert len(versions) == 10


def test_wake_contract_is_shared_but_android_audio_is_not() -> None:
    shared = read(SHARED / "src/commonMain/kotlin/com/personalassistant/shared/WakeContracts.kt")
    android = read(
        ANDROID / "src/main/java/com/personalassistant/android/wake/AndroidWakeWordEngine.kt"
    )
    assert "WakeActivationController" in shared
    assert "import android." not in shared
    assert "AudioRecord" in android


def test_single_activation_path_converges_before_phase9_voice() -> None:
    view_model = read(
        ANDROID / "src/main/java/com/personalassistant/android/ui/AssistantViewModel.kt"
    )
    manager = read(ANDROID / "src/main/java/com/personalassistant/android/wake/WakeWordManager.kt")
    all_android = "\n".join(
        read(path)
        for path in (ANDROID / "src/main/java").rglob("*.kt")
        if path.name != "VoiceSessionController.kt"
    )
    assert "container.wake.activateManual" in view_model
    assert "container.voice.start" not in view_model
    assert all_android.count("voice.start(") == 1
    assert "WakeActivationController" in manager


def test_detector_never_imports_backend_transport_or_provider() -> None:
    engine = read(
        ANDROID / "src/main/java/com/personalassistant/android/wake/AndroidWakeWordEngine.kt"
    )
    for forbidden in ("BackendApiClient", "VoiceTransport", "OkHttp", "WebSocket", "provider"):
        assert forbidden not in engine


def test_foreground_service_is_explicit_nonexported_microphone_service() -> None:
    manifest = read(ANDROID / "src/main/AndroidManifest.xml")
    assert "FOREGROUND_SERVICE_MICROPHONE" in manifest
    declaration = manifest.split('android:name=".wake.WakeWordForegroundService"', 1)[1]
    assert 'android:exported="false"' in declaration
    assert 'android:foregroundServiceType="microphone"' in declaration


def test_release_version_is_current() -> None:
    build = read(ANDROID / "build.gradle.kts")
    assert 'versionName = "0.13.0"' in build
    assert "versionCode = 130000" in build
    assert "APP_VERSION=0.13.0" in read(ROOT / ".env.example")


def test_no_wake_sdk_dependency_was_added_without_an_approved_model() -> None:
    catalog = read(MOBILE / "gradle/libs.versions.toml").casefold()
    build = read(ANDROID / "build.gradle.kts").casefold()
    for vendor in ("porcupine", "pocketsphinx", "vosk", "sherpa", "tensorflow"):
        assert vendor not in catalog
        assert vendor not in build


def test_fake_wake_engine_is_confined_to_test_sources() -> None:
    production = "\n".join(read(path) for path in MOBILE.rglob("src/*Main/**/*.kt"))
    tests = read(SHARED / "src/commonTest/kotlin/com/personalassistant/shared/WakeContractsTest.kt")
    assert "FakeWakeWordEngine" not in production
    assert "FakeWakeWordEngine" in tests
