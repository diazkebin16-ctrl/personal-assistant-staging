"""Exhaustive canonical Task state-transition matrix."""

import pytest

from backend.app.tasks.enums import TaskStatus
from backend.app.tasks.state_machine import TERMINAL_TASK_STATES, TaskStateMachine

ALLOWED = {
    TaskStatus.PENDING: {
        TaskStatus.QUEUED,
        TaskStatus.WAITING_CONNECTION,
        TaskStatus.WAITING_PERMISSION,
        TaskStatus.WAITING_CONFIRMATION,
        TaskStatus.CANCELLED,
        TaskStatus.EXPIRED,
    },
    TaskStatus.QUEUED: {
        TaskStatus.RUNNING,
        TaskStatus.WAITING_CONNECTION,
        TaskStatus.WAITING_PERMISSION,
        TaskStatus.WAITING_CONFIRMATION,
        TaskStatus.CANCELLED,
        TaskStatus.EXPIRED,
    },
    TaskStatus.WAITING_CONNECTION: {
        TaskStatus.QUEUED,
        TaskStatus.CANCELLED,
        TaskStatus.EXPIRED,
    },
    TaskStatus.WAITING_PERMISSION: {
        TaskStatus.QUEUED,
        TaskStatus.WAITING_CONFIRMATION,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
        TaskStatus.EXPIRED,
    },
    TaskStatus.WAITING_CONFIRMATION: {
        TaskStatus.QUEUED,
        TaskStatus.WAITING_PERMISSION,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
        TaskStatus.EXPIRED,
    },
    TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
    TaskStatus.EXPIRED: set(),
}


@pytest.mark.parametrize("current", list(TaskStatus))
@pytest.mark.parametrize("requested", list(TaskStatus))
def test_complete_state_transition_matrix(current: TaskStatus, requested: TaskStatus) -> None:
    evaluation = TaskStateMachine.evaluate(current, requested)
    assert evaluation.allowed is (requested in ALLOWED[current])
    assert evaluation.current_state is current
    assert evaluation.requested_state is requested


def test_terminal_states_have_no_outgoing_transitions() -> None:
    assert TERMINAL_TASK_STATES == {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.EXPIRED,
    }
    for terminal in TERMINAL_TASK_STATES:
        assert TaskStateMachine.allowed_targets(terminal) == frozenset()
