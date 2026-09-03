"""Phase 8 project and certified-backend integration boundary checks."""

import hashlib
from pathlib import Path

import pytest

from scripts.package_release import should_include

ROOT = Path(__file__).parents[2]
MOBILE = ROOT / "mobile"

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
}


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(("filename", "expected"), HISTORICAL_MIGRATIONS.items())
def test_historical_migration_remains_byte_identical(filename: str, expected: str) -> None:
    payload = (ROOT / "backend/migrations/versions" / filename).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == expected


def test_phase9_migration_is_nonempty_and_revises_text_assistant() -> None:
    migration = ROOT / "backend/migrations/versions/0009_realtime_voice.py"
    assert migration.stat().st_size > 1_000
    source = text(migration)
    assert 'down_revision: str | None = "0008_text_assistant"' in source
    assert "voice_sessions" in source and "voice_turns" in source


def test_professional_two_module_kmp_structure_exists() -> None:
    settings = text(MOBILE / "settings.gradle.kts")
    assert 'include(":shared", ":androidApp")' in settings
    assert (MOBILE / "shared/src/commonMain").is_dir()
    assert (MOBILE / "androidApp/src/main").is_dir()


def test_shared_module_contains_no_android_api() -> None:
    source = "\n".join(text(path) for path in (MOBILE / "shared/src/commonMain").rglob("*.kt"))
    assert "import android." not in source
    assert "WorkManager" not in source
    assert "ConnectivityManager" not in source
    assert "androidx.compose" not in source


def test_room_schema_is_versioned_and_exports_schema() -> None:
    database = text(
        MOBILE
        / "androidApp/src/main/java/com/personalassistant/android/data/local/AssistantDatabase.kt"
    )
    assert "version = 2" in database
    assert "exportSchema = true" in database


def test_conversation_cache_and_memory_remain_separate() -> None:
    entities = text(
        MOBILE / "androidApp/src/main/java/com/personalassistant/android/data/local/Entities.kt"
    )
    assert 'tableName = "conversations"' in entities
    assert 'tableName = "messages"' in entities
    assert "Memory" not in entities


def test_pending_operation_survives_process_recreation() -> None:
    entities = text(
        MOBILE / "androidApp/src/main/java/com/personalassistant/android/data/local/Entities.kt"
    )
    assert 'tableName = "pending_operations"' in entities
    for field in (
        "operationId",
        "idempotencyKey",
        "createdAtEpochMillis",
        "attemptCount",
        "lastAttemptAtEpochMillis",
        "status",
    ):
        assert field in entities


def test_connectivity_requires_validated_internet() -> None:
    monitor = text(
        MOBILE
        / "androidApp/src/main/java/com/personalassistant/android/connectivity"
        / "ConnectivityMonitor.kt"
    )
    assert "NET_CAPABILITY_INTERNET" in monitor
    assert "NET_CAPABILITY_VALIDATED" in monitor
    assert "ConnectivityState.DEGRADED" in monitor
    assert "ConnectivityState.UNKNOWN" in monitor


def test_device_registration_reuses_certified_identity_api() -> None:
    client = text(MOBILE / "shared/src/commonMain/kotlin/com/personalassistant/shared/Network.kt")
    backend = text(ROOT / "backend/app/identity/api.py")
    assert "/api/v1/devices/register" in client
    assert '@router.post("/devices/register"' in backend


@pytest.mark.parametrize(
    "endpoint",
    ["/api/v1/conversations", "/api/v1/conversations/$conversationId/messages"],
)
def test_android_uses_only_certified_text_assistant_endpoints(endpoint: str) -> None:
    client = text(MOBILE / "shared/src/commonMain/kotlin/com/personalassistant/shared/Network.kt")
    assert endpoint in client


def test_android_submission_carries_expected_version_and_idempotency() -> None:
    contracts = text(
        MOBILE / "shared/src/commonMain/kotlin/com/personalassistant/shared/Contracts.kt"
    )
    assert '@SerialName("idempotency_key")' in contracts
    assert '@SerialName("expected_version")' in contracts


def test_device_and_user_remain_distinct_entities() -> None:
    registration = (
        text(MOBILE / "shared/src/commonMain/kotlin/com/personalassistant/shared/Contracts.kt")
        .split("data class DeviceRegistrationRequest", 1)[1]
        .split("@Serializable", 1)[0]
    )
    assert "userId" not in registration
    assert "deviceIdentifier" in registration


def test_android_version_is_current() -> None:
    build = text(MOBILE / "androidApp/build.gradle.kts")
    assert 'versionName = "0.13.0"' in build
    assert "versionCode = 130000" in build


def test_env_example_is_present_and_packaging_is_deterministic() -> None:
    template = ROOT / ".env.example"
    assert template.is_file()
    assert "APP_VERSION=0.13.0" in text(template)
    assert should_include(Path(".env.example"))
    assert not should_include(Path(".env"))


def test_android_ci_runs_unit_lint_debug_and_release_validation() -> None:
    ci = text(ROOT / ".github/workflows/ci.yml")
    for task in (
        ":shared:desktopTest",
        ":androidApp:testLocalDebugUnitTest",
        ":androidApp:lintLocalDebug",
        ":androidApp:assembleLocalDebug",
        ":androidApp:assembleProductionRelease",
    ):
        assert task in ci


def test_phase10_extends_the_phase9_voice_controller_without_parallel_voice() -> None:
    source = "\n".join(text(path) for path in MOBILE.rglob("*.kt") if "build" not in path.parts)
    assert source.count("class VoiceSessionController(") == 1
    assert "WakeVoicePipeline" not in source
    assert "WakeOrchestrator" not in source


def test_phase8_has_no_external_executor_implementation() -> None:
    names = {path.name.lower() for path in MOBILE.rglob("*") if path.is_file()}
    assert not any(name == "executor.kt" or name == "financialexecutor.kt" for name in names)
