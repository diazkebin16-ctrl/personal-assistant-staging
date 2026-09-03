"""Phase 11 authority, replay, tamper, privacy, and account-boundary attacks."""

import hashlib
from pathlib import Path

ROOT = Path(__file__).parents[2]
ANDROID = ROOT / "mobile/androidApp/src/main/java/com/personalassistant/android"
SHARED = ROOT / "mobile/shared/src/commonMain/kotlin/com/personalassistant/shared"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def all_mobile_source() -> str:
    return "\n".join(
        read(path) for path in (ROOT / "mobile").rglob("*.kt") if "build" not in path.parts
    )


def test_offline_queue_stores_encrypted_payload() -> None:
    entity = read(ANDROID / "data/local/Entities.kt")
    repository = read(ANDROID / "data/ConversationRepository.kt")
    assert "encryptedPayload: ByteArray" in entity
    assert "contentCipher.encrypt(content)" in repository


def test_queue_does_not_store_access_or_refresh_tokens() -> None:
    entity = read(ANDROID / "data/local/Entities.kt")
    assert "accessToken" not in entity and "refreshToken" not in entity


def test_queue_does_not_store_confirmation_or_permission_authority() -> None:
    entity = read(ANDROID / "data/local/Entities.kt")
    assert "permissionGranted" not in entity
    assert "confirmationValid" not in entity
    assert "safeModeAllows" not in entity


def test_payload_integrity_uses_sha256() -> None:
    source = read(ANDROID / "data/PayloadIntegrity.kt")
    assert 'MessageDigest.getInstance("SHA-256")' in source


def test_payload_fingerprint_binds_sensitive_metadata() -> None:
    source = read(ANDROID / "data/PayloadIntegrity.kt")
    for field in (
        "operationType",
        "conversationId",
        "idempotencyKey",
        "expectedVersion",
        "content",
    ):
        assert field in source


def test_tampered_ciphertext_fails_terminally() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    assert "PAYLOAD_AUTHENTICATION_FAILED" in source
    assert "OfflineOperationState.TERMINAL_FAILURE" in source


def test_mutated_envelope_fails_terminally() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    assert "PAYLOAD_INTEGRITY_FAILED" in source
    assert "hasValidEnvelope" in source


def test_same_idempotency_key_cannot_change_operation_id() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    assert 'idempotencyKey != "android:$operationId"' in source


def test_unknown_payload_version_fails_closed() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    assert "payloadVersion != CURRENT_PAYLOAD_VERSION" in source


def test_unknown_persisted_state_fails_closed() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    assert "OfflineOperationState.valueOf(status)" in source
    assert "getOrNull()" in source


def test_cross_user_replay_is_blocked_before_network() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    binding_check = source.index("operation.ownerId != binding.userId")
    network_call = source.index("api.submitMessage")
    assert binding_check < network_call


def test_cross_device_replay_is_blocked_before_network() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    binding_check = source.index("operation.deviceId != binding.deviceId")
    network_call = source.index("api.submitMessage")
    assert binding_check < network_call


def test_atomic_database_claim_rechecks_identity() -> None:
    source = read(ANDROID / "data/local/Daos.kt")
    assert "ownerId = :ownerId AND deviceId = :deviceId" in source


def test_duplicate_worker_cannot_claim_syncing_row() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    states = source.split("private val WORKER_CLAIM_STATES", 1)[0]
    assert "OfflineOperationState.SYNCING" not in states.rsplit("ACTIVE_PRE_SYNC_STATES", 1)[1]


def test_duplicate_callback_cannot_overwrite_terminal_state() -> None:
    source = read(ANDROID / "data/local/Daos.kt")
    acknowledge = source.split("suspend fun acknowledge", 1)[0].rsplit("@Query", 1)[1]
    assert "status IN (:fromStates)" in acknowledge


def test_401_is_not_automatically_retryable() -> None:
    source = read(SHARED / "OfflineSemantics.kt")
    auth_branch = source.split("ErrorCategory.AUTHENTICATION", 1)[1].split(
        "ErrorCategory.CONFLICT", 1
    )[0]
    assert "AUTH_REQUIRED" in auth_branch and "RETRYABLE" not in auth_branch


def test_403_is_not_automatically_retryable() -> None:
    source = read(SHARED / "OfflineSemantics.kt")
    assert "ErrorCategory.AUTHORIZATION" in source
    assert "OfflineFailureDisposition.REJECTED" in source


def test_idempotency_conflict_is_not_retried() -> None:
    source = read(SHARED / "OfflineSemantics.kt")
    assert "ErrorCategory.CONFLICT -> OfflineFailureDisposition.CONFLICT" in source


def test_validation_failure_is_not_retried() -> None:
    source = read(SHARED / "OfflineSemantics.kt")
    retryable_set = source.split("failure.category in setOf(", 2)[2].split(") &&", 1)[0]
    assert "VALIDATION" not in retryable_set


def test_confirmation_expiration_is_rejected() -> None:
    source = read(SHARED / "OfflineSemantics.kt")
    assert "ErrorCategory.CONFIRMATION_REQUIRED" in source
    assert "OfflineFailureDisposition.REJECTED" in source


def test_permission_revocation_is_rejected() -> None:
    source = read(SHARED / "OfflineSemantics.kt")
    assert "ErrorCategory.PERMISSION_REQUIRED" in source


def test_safe_mode_denial_is_rejected() -> None:
    source = read(SHARED / "OfflineSemantics.kt")
    assert "ErrorCategory.SAFE_MODE" in source


def test_device_revocation_clears_session_cache_and_work() -> None:
    repository = read(ANDROID / "data/ConversationRepository.kt")
    logout = read(ANDROID / "auth/LogoutCoordinator.kt")
    assert "onDeviceRevoked()" in repository
    assert "suspend fun deviceRevoked() = logout()" in logout
    assert "cancelAllWorkByTag" in logout and "database.clearAllTables()" in logout


def test_logout_waits_for_work_cancellation_before_clear() -> None:
    source = read(ANDROID / "auth/LogoutCoordinator.kt")
    logout = source.split("suspend fun logout", 1)[1].split("suspend fun deviceRevoked", 1)[0]
    assert logout.index("cancelAllWorkByTag") < logout.index("database.clearAllTables")
    assert ".await()" in logout


def test_account_switch_clears_old_local_authority() -> None:
    source = read(ANDROID / "auth/LogoutCoordinator.kt")
    bind = source.split("suspend fun bindAuthenticated", 1)[1].split("suspend fun logout", 1)[0]
    assert "previous != binding" in bind
    assert "database.clearAllTables()" in bind


def test_auth_expiration_preserves_pending_intent_but_stops_work() -> None:
    source = read(ANDROID / "auth/LogoutCoordinator.kt")
    expired = source.split("suspend fun authenticationExpired", 1)[1]
    assert "cancelAllWorkByTag" in expired
    assert "clearCredentialsPreservingAuthority" in expired
    assert "database.clearAllTables" not in expired


def test_cancel_race_never_fabricates_server_cancellation() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    race = source.split("stateOrNull() == OfflineOperationState.CANCEL_REQUESTED", 1)[1].split(
        "val disposition", 1
    )[0]
    assert "TerminalFailure" in race
    assert "ACKNOWLEDGED" not in race and "CANCELLED" not in race


def test_server_ack_can_converge_after_cancellation_request() -> None:
    source = read(ANDROID / "data/ConversationRepository.kt")
    ack = source.split("dao.acknowledge", 1)[1].split("DeliveryResult.Success", 1)[0]
    assert "CANCEL_REQUESTED" in ack


def test_offline_ui_does_not_fabricate_assistant_answer() -> None:
    repository = read(ANDROID / "data/ConversationRepository.kt")
    enqueue = repository.split("suspend fun enqueueMessage", 1)[1].split(
        "suspend fun retryDelivery", 1
    )[0]
    assert "AssistantResponse" not in enqueue
    assert "Answered" not in enqueue


def test_no_raw_audio_is_added_to_offline_storage() -> None:
    entity = read(ANDROID / "data/local/Entities.kt").lower()
    assert "pcm" not in entity and "rawaudio" not in entity and "audiopayload" not in entity


def test_no_offline_cloud_wake_fallback() -> None:
    wake = read(ANDROID / "wake/WakeWordManager.kt")
    assert "ConnectivityState.ONLINE" in wake
    assert "CloudWake" not in all_mobile_source()


def test_no_general_executor_is_added() -> None:
    names = {path.name.lower() for path in ROOT.rglob("*") if path.is_file()}
    assert "executor.kt" not in names
    assert "financialexecutor.kt" not in names
    assert "offlineexecutor.kt" not in names


def test_financial_boundary_remains_absolute() -> None:
    source = read(SHARED / "SecuritySemantics.kt")
    assert "fun canExecuteExternalAction" in source
    assert "= false" in source
    for action in ("buy", "sell", "transfer", "withdraw", "deposit", "place_order"):
        assert f'"{action}"' in source


def test_local_cache_cannot_mutate_server_memory_or_task() -> None:
    source = read(SHARED / "SecuritySemantics.kt")
    assert "canMutateServerTask(): Boolean = false" in source
    assert "canMutateServerMemory(): Boolean = false" in source


def test_critical_cache_is_not_stale_displayable() -> None:
    source = read(SHARED / "OfflineSemantics.kt")
    assert "sensitivity != DataSensitivity.CRITICAL" in source


def test_migrations_0001_through_0009_remain_certified() -> None:
    expected = {
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
        "0008_text_assistant.py": (
            "2e8edbd5bf9e3e474375d74c79e5f5d0e70931824d73a0d9133f090524a0d337"
        ),
        "0009_realtime_voice.py": (
            "5f8da86ac7fa46f48ca417176a782e0ff3ad41fc800b49952777ae8574cbbea9"
        ),
    }
    for name, digest in expected.items():
        assert (
            hashlib.sha256((ROOT / "backend/migrations/versions" / name).read_bytes()).hexdigest()
            == digest
        )


def test_no_backend_schema_change_after_phase11() -> None:
    versions = ROOT / "backend/migrations/versions"
    assert (versions / "0010_web_research.py").is_file()
    assert len(list(versions.glob("*.py"))) == 10
    assert not (ROOT / "backend/migrations/versions/0010_web_client.py").exists()
