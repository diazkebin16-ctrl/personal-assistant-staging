"""Explicit deterministic state machine for Task lifecycle transitions."""

from dataclasses import dataclass

from backend.app.tasks.enums import TaskStatus

TERMINAL_TASK_STATES = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.EXPIRED}
)

_ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset(
        {
            TaskStatus.QUEUED,
            TaskStatus.WAITING_CONNECTION,
            TaskStatus.WAITING_PERMISSION,
            TaskStatus.WAITING_CONFIRMATION,
            TaskStatus.CANCELLED,
            TaskStatus.EXPIRED,
        }
    ),
    TaskStatus.QUEUED: frozenset(
        {
            TaskStatus.RUNNING,
            TaskStatus.WAITING_CONNECTION,
            TaskStatus.WAITING_PERMISSION,
            TaskStatus.WAITING_CONFIRMATION,
            TaskStatus.CANCELLED,
            TaskStatus.EXPIRED,
        }
    ),
    TaskStatus.WAITING_CONNECTION: frozenset(
        {TaskStatus.QUEUED, TaskStatus.CANCELLED, TaskStatus.EXPIRED}
    ),
    TaskStatus.WAITING_PERMISSION: frozenset(
        {
            TaskStatus.QUEUED,
            TaskStatus.WAITING_CONFIRMATION,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
            TaskStatus.EXPIRED,
        }
    ),
    TaskStatus.WAITING_CONFIRMATION: frozenset(
        {
            TaskStatus.QUEUED,
            TaskStatus.WAITING_PERMISSION,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
            TaskStatus.EXPIRED,
        }
    ),
    TaskStatus.RUNNING: frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED}),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
    TaskStatus.EXPIRED: frozenset(),
}


@dataclass(frozen=True)
class TaskTransitionEvaluation:
    current_state: TaskStatus
    requested_state: TaskStatus
    allowed: bool
    reason: str


class TaskStateMachine:
    """The only source of truth for Task state transitions."""

    @staticmethod
    def evaluate(current: TaskStatus, requested: TaskStatus) -> TaskTransitionEvaluation:
        allowed = requested in _ALLOWED_TRANSITIONS[current]
        reason = "TRANSITION_ALLOWED" if allowed else "INVALID_TASK_TRANSITION"
        return TaskTransitionEvaluation(current, requested, allowed, reason)

    @staticmethod
    def is_terminal(status: TaskStatus) -> bool:
        return status in TERMINAL_TASK_STATES

    @staticmethod
    def allowed_targets(status: TaskStatus) -> frozenset[TaskStatus]:
        return _ALLOWED_TRANSITIONS[status]
