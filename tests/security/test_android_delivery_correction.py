"""Certification checks for the single durable Android delivery path."""

from pathlib import Path

ROOT = Path(__file__).parents[2]
ANDROID = ROOT / "mobile/androidApp/src/main/java/com/personalassistant/android"
VIEW_MODEL = ANDROID / "ui/AssistantViewModel.kt"
REPOSITORY = ANDROID / "data/ConversationRepository.kt"
SCHEDULER = ANDROID / "work/DeliveryScheduler.kt"
WORKER = ANDROID / "work/MessageDeliveryWorker.kt"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def retry_boundary() -> str:
    source = read(REPOSITORY)
    return source.split("suspend fun retryDelivery", 1)[1].split(
        "/** Internal delivery boundary", 1
    )[0]


def test_ui_retry_does_not_call_network_delivery_directly() -> None:
    source = read(VIEW_MODEL)
    retry = source.split("fun retry(operationId: String)", 1)[1].split("fun confirm", 1)[0]
    assert ".deliver(" not in retry


def test_ui_retry_uses_repository_rescheduling_boundary() -> None:
    assert "container.conversations.retryDelivery(operationId)" in read(VIEW_MODEL)


def test_retry_schedules_the_existing_operation_id() -> None:
    boundary = retry_boundary()
    assert "scheduler.schedule(operation.operationId)" in boundary
    assert "scheduler.schedule(operationId)" not in boundary


def test_retry_preserves_the_stored_idempotency_key() -> None:
    boundary = retry_boundary()
    assert "idempotencyKey" not in boundary
    assert "update" not in boundary


def test_worker_is_the_only_network_delivery_caller() -> None:
    call_sites = []
    for path in ANDROID.rglob("*.kt"):
        if ".deliver(" in read(path):
            call_sites.append(path.relative_to(ANDROID).as_posix())
    assert call_sites == ["work/MessageDeliveryWorker.kt"]


def test_retryable_waiting_operation_remains_durably_schedulable() -> None:
    boundary = retry_boundary()
    assert "WAITING_CONNECTION" not in boundary
    assert "MANUAL_RETRY_STATES" in boundary
    assert "scheduler.schedule" in boundary


def test_two_retry_taps_cannot_create_two_logical_operations() -> None:
    boundary = retry_boundary()
    assert "UUID.randomUUID" not in boundary
    assert ".insert(" not in boundary
    assert "operation.operationId" in boundary


def test_unique_work_prevents_duplicate_workers_for_one_operation() -> None:
    scheduler = read(SCHEDULER)
    assert "enqueueUniqueWork(uniqueWorkName(operationId), ExistingWorkPolicy.KEEP" in scheduler
    assert '"message:$operationId"' in scheduler


def test_late_ui_failure_cannot_overwrite_worker_success() -> None:
    view_model = read(VIEW_MODEL)
    assert "updateStatus" not in view_model
    assert ".deliver(" not in view_model


def test_retry_is_durable_before_ui_reports_it_scheduled() -> None:
    boundary = retry_boundary()
    assert boundary.index("scheduler.schedule(operation.operationId)") < boundary.index(
        "RetryScheduleResult.Scheduled"
    )
    assert "updateStatus" not in boundary
    scheduler = read(SCHEDULER)
    assert "suspend fun schedule" in scheduler
    assert ".await()" in scheduler


def test_backend_idempotency_remains_defense_in_depth() -> None:
    repository = read(REPOSITORY)
    assert "idempotencyKey = claimedOperation.idempotencyKey" in repository
    assert "expectedVersion = claimedOperation.expectedVersion" in repository


def test_obsolete_secondary_delivery_entry_is_removed() -> None:
    repository = read(REPOSITORY)
    assert "deliverPending" not in repository
    assert "DeliveryResult.Retry" in read(WORKER)
    assert "OfflineOperationState.RETRYABLE_FAILURE" in repository
