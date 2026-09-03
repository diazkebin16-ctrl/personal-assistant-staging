"""Exhaustive deterministic transition and terminal-state tests."""

import pytest

from backend.app.core.errors import InvalidOrchestrationTransitionError
from backend.app.orchestrator.enums import OrchestrationState
from backend.app.orchestrator.state_machine import OrchestrationStateMachine

ALLOWED: set[tuple[OrchestrationState, OrchestrationState]] = {
    (source, target)
    for source, targets in OrchestrationStateMachine._ALLOWED.items()
    for target in targets
}


@pytest.mark.parametrize("source,target", list(ALLOWED))
def test_every_declared_transition_is_allowed(
    source: OrchestrationState, target: OrchestrationState
) -> None:
    OrchestrationStateMachine.require(source, target)


@pytest.mark.parametrize(
    "source,target",
    [
        (source, target)
        for source in OrchestrationState
        for target in OrchestrationState
        if source != target and (source, target) not in ALLOWED
    ],
)
def test_every_undeclared_transition_is_rejected(
    source: OrchestrationState, target: OrchestrationState
) -> None:
    with pytest.raises(InvalidOrchestrationTransitionError):
        OrchestrationStateMachine.require(source, target)


@pytest.mark.parametrize(
    "state",
    [
        OrchestrationState.COMPLETED_NO_ACTION,
        OrchestrationState.DENIED,
        OrchestrationState.FAILED,
        OrchestrationState.CANCELLED,
        OrchestrationState.EXPIRED,
    ],
)
def test_terminal_states_cannot_be_resurrected(state: OrchestrationState) -> None:
    assert OrchestrationStateMachine.is_terminal(state)
    with pytest.raises(InvalidOrchestrationTransitionError):
        OrchestrationStateMachine.require(state, OrchestrationState.RECEIVED)


def test_ready_is_a_future_handoff_not_task_completion() -> None:
    assert not OrchestrationStateMachine.is_terminal(OrchestrationState.READY_FOR_EXECUTION)
    with pytest.raises(InvalidOrchestrationTransitionError):
        OrchestrationStateMachine.require(
            OrchestrationState.READY_FOR_EXECUTION,
            OrchestrationState.COMPLETED_NO_ACTION,
        )
