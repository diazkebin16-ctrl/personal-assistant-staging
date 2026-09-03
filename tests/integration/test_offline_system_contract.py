"""Phase 11 durable transport, recovery, UX, and migration contracts."""

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
ANDROID = ROOT / "mobile/androidApp/src/main/java/com/personalassistant/android"
SHARED = ROOT / "mobile/shared/src/commonMain/kotlin/com/personalassistant/shared"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_connectivity_model_has_all_required_states() -> None:
    source = read(SHARED / "SecuritySemantics.kt")
    for state in ("ONLINE", "OFFLINE", "DEGRADED", "RECOVERING", "UNKNOWN"):
        assert state in source


def test_validated_interface_enters_recovering_not_online() -> None:
    source = read(ANDROID / "connectivity/ConnectivityMonitor.kt")
    assert "NET_CAPABILITY_VALIDATED" in source
    assert ") ConnectivityState.RECOVERING" in source
    assert ") ConnectivityState.ONLINE" not in source


def test_backend_probe_establishes_online() -> None:
    source = read(ANDROID / "connectivity/ConnectivityCoordinator.kt")
    assert "backend.health()" in source
    assert "is ApiResult.Success -> _state.value = ConnectivityState.ONLINE" in source


def test_connectivity_is_event_driven() -> None:
    source = read(ANDROID / "connectivity/ConnectivityMonitor.kt")
    assert "NetworkCallback" in source and "awaitClose" in source
    assert "while (" not in source and "delay(" not in source


def test_room_schema_is_incremental() -> None:
    source = read(ANDROID / "data/local/AssistantDatabase.kt")
    assert "version = 2" in source
    assert "exportSchema = true" in source
    schema = json.loads(
        read(
            ROOT
            / "mobile/androidApp/schemas"
            / "com.personalassistant.android.data.local.AssistantDatabase/2.json"
        )
    )
    assert schema["database"]["version"] == 2


def test_room_schema_export_uses_gradle_plugin() -> None:
    build = read(ROOT / "mobile/androidApp/build.gradle.kts")
    assert "alias(libs.plugins.room)" in build
    assert 'room { schemaDirectory("$projectDir/schemas") }' in build
    assert "room.schemaLocation" not in build
    assert "afterEvaluate" in build and "zipWithNext" in build and "mustRunAfter" in build
    assert 'exclude("**/byRounds/**")' in build


def test_room_1_to_2_migration_is_registered() -> None:
    container = read(ANDROID / "AppContainer.kt")
    migration = read(ANDROID / "data/local/DatabaseMigrations.kt")
    assert ".addMigrations(MIGRATION_1_2)" in container
    assert "Migration(1, 2)" in migration
    assert "fallbackToDestructiveMigration" not in container


def test_migration_converts_phase8_states() -> None:
    source = read(ANDROID / "data/local/DatabaseMigrations.kt")
    for old, new in (
        ("WAITING_CONNECTION", "WAITING_FOR_NETWORK"),
        ("IN_FLIGHT", "RETRYABLE_FAILURE"),
        ("SUCCEEDED", "ACKNOWLEDGED"),
        ("FAILED", "TERMINAL_FAILURE"),
    ):
        assert old in source and new in source


def test_legacy_unbound_active_rows_fail_closed() -> None:
    source = read(ANDROID / "data/local/DatabaseMigrations.kt")
    assert "LEGACY_IDENTITY_UNBOUND" in source
    assert "status = 'REJECTED'" in source


def test_pending_operation_has_stable_identity_metadata() -> None:
    source = read(ANDROID / "data/local/Entities.kt")
    for field in ("operationId", "idempotencyKey", "operationType", "payloadVersion"):
        assert field in source


def test_pending_operation_has_owner_device_binding() -> None:
    source = read(ANDROID / "data/local/Entities.kt")
    assert "ownerId" in source and "deviceId" in source


def test_pending_operation_has_attempt_and_ack_metadata() -> None:
    source = read(ANDROID / "data/local/Entities.kt")
    for field in (
        "attemptCount",
        "lastAttemptAtEpochMillis",
        "nextAttemptAtEpochMillis",
        "serverAcknowledgedAtEpochMillis",
    ):
        assert field in source


def test_new_intent_creates_one_operation_identity() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    enqueue = source.split("suspend fun enqueueMessage", 1)[1].split(
        "suspend fun retryDelivery", 1
    )[0]
    assert enqueue.count("UUID.randomUUID()") == 1
    assert 'idempotencyKey = "android:$operationId"' in enqueue


def test_retry_reuses_stored_operation_identity() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    retry = source.split("suspend fun retryDelivery", 1)[1].split("suspend fun cancel", 1)[0]
    assert "UUID.randomUUID" not in retry
    assert "scheduler.schedule(operation.operationId)" in retry


def test_worker_only_delivery_path_is_preserved() -> None:
    callers = []
    for path in ANDROID.rglob("*.kt"):
        if ".deliver(" in read(path):
            callers.append(path.relative_to(ANDROID).as_posix())
    assert callers == ["work/MessageDeliveryWorker.kt"]


def test_workmanager_uses_connected_constraint() -> None:
    source = read(ANDROID / "work/DeliveryScheduler.kt")
    assert "NetworkType.CONNECTED" in source


def test_workmanager_uses_unique_keep_identity() -> None:
    source = read(ANDROID / "work/DeliveryScheduler.kt")
    assert "enqueueUniqueWork(uniqueWorkName(operationId), ExistingWorkPolicy.KEEP" in source
    assert '"message:$operationId"' in source


def test_workmanager_backoff_is_bounded_by_attempt_policy() -> None:
    scheduler = read(ANDROID / "work/DeliveryScheduler.kt")
    worker = read(ANDROID / "work/MessageDeliveryWorker.kt")
    assert "BackoffPolicy.EXPONENTIAL" in scheduler
    assert "runAttemptCount >= ConversationRepository.MAX_ATTEMPTS" in worker


def test_atomic_claim_prevents_duplicate_workers() -> None:
    source = read(ANDROID / "data/local/Daos.kt")
    assert "claimForSync" in source
    assert "status IN (:eligibleStates)" in source
    assert "attemptCount < :maxAttempts" in source


def test_atomic_claim_enforces_owner_and_device() -> None:
    source = read(ANDROID / "data/local/Daos.kt")
    claim = source.split("suspend fun claimForSync", 1)[0].rsplit("@Query", 1)[1]
    assert "ownerId = :ownerId" in claim
    assert "deviceId = :deviceId" in claim


def test_process_death_recovery_is_explicit() -> None:
    source = read(ANDROID / "sync/OfflineSyncCoordinator.kt")
    assert "recoverInterruptedSync" in source
    assert "PROCESS_INTERRUPTED_DURING_SYNC" in source


def test_reconnect_scheduling_is_serialized() -> None:
    source = read(ANDROID / "sync/OfflineSyncCoordinator.kt")
    assert "coordinationMutex" in source and "withLock" in source


def test_reconnect_does_not_flush_auth_required_rows() -> None:
    source = read(ANDROID / "sync/OfflineSyncCoordinator.kt")
    eligible = source.split("private val ELIGIBLE_STATES", 1)[1].split(
        "private val TERMINAL_STATES", 1
    )[0]
    assert "AUTH_REQUIRED" not in eligible


def test_retry_policy_is_bounded_and_jittered() -> None:
    source = read(SHARED / "OfflineSemantics.kt")
    assert "const val maxAttempts = 5" in source
    assert "stableBucket" in source and "maxDelayMillis" in source


def test_transient_failures_use_retry_state() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    assert "OfflineOperationState.RETRYABLE_FAILURE" in source
    assert "DeliveryResult.Retry" in source


def test_authentication_failure_waits_without_retry_loop() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    assert "OfflineOperationState.AUTH_REQUIRED" in source
    assert "DeliveryResult.AuthenticationRequired" in source


def test_server_ack_and_cache_commit_share_transaction() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    delivery = source.split("internal suspend fun deliver", 1)[1].split(
        "private suspend fun handleFailure", 1
    )[0]
    success = delivery.split("is ApiResult.Success ->", 1)[1].split("is ApiResult.Failure ->", 1)[0]
    assert "database.withTransaction" in success
    assert "dao.acknowledge" in success


def test_ambiguous_commit_reuses_server_idempotency() -> None:
    client = read(ANDROID / "data/ConversationRepository.kt")
    backend = read(ROOT / "backend/app/text_assistant/service.py")
    assert "idempotencyKey = claimedOperation.idempotencyKey" in client
    assert "_idempotent_existing" in backend
    assert backend.index("_idempotent_existing") < backend.index("request.expected_version")


def test_cancel_before_claim_uses_canonical_repository() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    cancel = source.split("suspend fun cancel", 1)[1].split("/** Internal delivery boundary", 1)[0]
    assert "OfflineOperationState.CANCELLED" in cancel
    assert "scheduler.cancel(operation.operationId)" in cancel


def test_cancel_send_race_is_truthfully_ambiguous() -> None:
    repository = read(ANDROID / "data/ConversationRepository.kt")
    ui = read(ANDROID / "ui/PersonalAssistantApp.kt")
    assert "OfflineOperationState.CANCEL_REQUESTED" in repository
    assert "server result unknown" in ui


def test_text_ui_distinguishes_required_states() -> None:
    source = read(ANDROID / "ui/PersonalAssistantApp.kt")
    for label in (
        "Saved locally",
        "Waiting for a secure connection",
        "Synchronizing",
        "Accepted by the server",
        "Rejected by the server",
        "Sign-in required",
    ):
        assert label in source


def test_voice_refuses_unverified_connection() -> None:
    source = read(ANDROID / "ui/AssistantViewModel.kt")
    voice = source.split("fun startVoice", 1)[1].split("fun enableWake", 1)[0]
    assert "connectivity.value != ConnectivityState.ONLINE" in voice
    assert "VoiceUnavailableOffline" in voice


def test_wake_gateway_refuses_offline_voice() -> None:
    source = read(ANDROID / "wake/WakeWordManager.kt")
    assert "connectivity.value != ConnectivityState.ONLINE" in source
    assert "voice.start" in source


def test_cache_and_queue_are_bounded() -> None:
    source = read(SHARED / "OfflineSemantics.kt")
    assert "maxActiveOperations = 100" in source
    assert "maxMessagesPerConversation = 200" in source
    assert "terminalRetentionMillis" in source


def test_phase11_does_not_add_backend_migration() -> None:
    versions = ROOT / "backend/migrations/versions"
    assert not (versions / "0010_offline_system.py").exists()
    assert (versions / "0010_web_research.py").is_file()
    assert len(list(versions.glob("*.py"))) == 10


def test_project_version_remains_coherent_after_phase11() -> None:
    assert 'version = "0.13.0"' in read(ROOT / "pyproject.toml")
    assert 'versionName = "0.13.0"' in read(ROOT / "mobile/androidApp/build.gradle.kts")
    assert "APP_VERSION=0.13.0" in read(ROOT / ".env.example")


def test_offline_architecture_is_documented() -> None:
    source = read(ROOT / "docs/architecture/offline-system.md")
    for topic in ("source of truth", "State machine", "Retry and reconciliation", "multi-device"):
        assert topic.lower() in source.lower()
