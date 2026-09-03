"""Central deterministic lifecycle for coordination state, separate from Task state."""

from backend.app.core.errors import InvalidOrchestrationTransitionError
from backend.app.orchestrator.enums import OrchestrationState


class OrchestrationStateMachine:
    TERMINAL = frozenset(
        {
            OrchestrationState.COMPLETED_NO_ACTION,
            OrchestrationState.DENIED,
            OrchestrationState.FAILED,
            OrchestrationState.CANCELLED,
            OrchestrationState.EXPIRED,
        }
    )
    _ALLOWED = {
        OrchestrationState.RECEIVED: frozenset(
            {
                OrchestrationState.CONTEXT_PREPARED,
                OrchestrationState.DENIED,
                OrchestrationState.FAILED,
                OrchestrationState.CANCELLED,
                OrchestrationState.EXPIRED,
            }
        ),
        OrchestrationState.CONTEXT_PREPARED: frozenset(
            {
                OrchestrationState.ROUTED,
                OrchestrationState.DENIED,
                OrchestrationState.FAILED,
                OrchestrationState.CANCELLED,
                OrchestrationState.EXPIRED,
            }
        ),
        OrchestrationState.ROUTED: frozenset(
            {
                OrchestrationState.PROPOSAL_GENERATED,
                OrchestrationState.DENIED,
                OrchestrationState.FAILED,
                OrchestrationState.CANCELLED,
                OrchestrationState.EXPIRED,
            }
        ),
        OrchestrationState.PROPOSAL_GENERATED: frozenset(
            {
                OrchestrationState.PLAN_VALIDATED,
                OrchestrationState.COMPLETED_NO_ACTION,
                OrchestrationState.DENIED,
                OrchestrationState.FAILED,
                OrchestrationState.CANCELLED,
                OrchestrationState.EXPIRED,
            }
        ),
        OrchestrationState.PLAN_VALIDATED: frozenset(
            {
                OrchestrationState.WAITING_PERMISSION,
                OrchestrationState.WAITING_CONFIRMATION,
                OrchestrationState.READY_FOR_EXECUTION,
                OrchestrationState.DENIED,
                OrchestrationState.FAILED,
                OrchestrationState.CANCELLED,
                OrchestrationState.EXPIRED,
            }
        ),
        OrchestrationState.WAITING_PERMISSION: frozenset(
            {
                OrchestrationState.WAITING_CONFIRMATION,
                OrchestrationState.READY_FOR_EXECUTION,
                OrchestrationState.DENIED,
                OrchestrationState.CANCELLED,
                OrchestrationState.EXPIRED,
            }
        ),
        OrchestrationState.WAITING_CONFIRMATION: frozenset(
            {
                OrchestrationState.READY_FOR_EXECUTION,
                OrchestrationState.DENIED,
                OrchestrationState.CANCELLED,
                OrchestrationState.EXPIRED,
            }
        ),
        OrchestrationState.READY_FOR_EXECUTION: frozenset(
            {OrchestrationState.CANCELLED, OrchestrationState.EXPIRED}
        ),
    }

    @classmethod
    def is_terminal(cls, state: OrchestrationState) -> bool:
        return state in cls.TERMINAL

    @classmethod
    def require(cls, current: OrchestrationState, target: OrchestrationState) -> None:
        if target not in cls._ALLOWED.get(current, frozenset()):
            raise InvalidOrchestrationTransitionError
