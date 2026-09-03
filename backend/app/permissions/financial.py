"""Non-overridable Phase 2 financial execution safeguard."""

from backend.app.permissions.models import Capability


class FinancialExecutionGuard:
    """Deny financial execution regardless of permission or auto-execute metadata."""

    def blocks(self, capability: Capability) -> bool:
        return capability.financial and capability.external_side_effect
