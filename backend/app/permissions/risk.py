"""Deterministic, caller-independent risk classification."""

from backend.app.identity.context import IdentityContext
from backend.app.permissions.enums import RiskLevel
from backend.app.permissions.models import Capability
from backend.app.permissions.schemas import PermissionScope, RiskAssessment


class RiskEngine:
    """Compute authoritative risk from server-owned capability attributes."""

    def evaluate(
        self,
        *,
        capability: Capability,
        action: str,
        scope: PermissionScope,
        identity: IdentityContext,
        context: dict[str, str | int | float | bool | None],
    ) -> RiskAssessment:
        if not capability.allows_operations((action,)):
            raise ValueError("Action is outside the server-owned capability vocabulary")
        del scope, identity, context  # Untrusted context cannot lower server-owned risk.
        level = RiskLevel(capability.default_risk_level)
        reasons = [f"CAPABILITY_DEFAULT_{level.name}"]

        if capability.privacy_impact and level < RiskLevel.MODERATE:
            level = RiskLevel.MODERATE
            reasons.append("PRIVACY_IMPACT_FLOOR")
        if capability.external_side_effect and level < RiskLevel.ELEVATED:
            level = RiskLevel.ELEVATED
            reasons.append("EXTERNAL_SIDE_EFFECT_FLOOR")
        if capability.data_destructive and level < RiskLevel.HIGH:
            level = RiskLevel.HIGH
            reasons.append("DATA_DESTRUCTIVE_FLOOR")
        if capability.financial and capability.external_side_effect:
            level = RiskLevel.CRITICAL
            reasons.append("FINANCIAL_EXECUTION_FLOOR")

        return RiskAssessment(
            risk_level=level,
            reversible=not capability.data_destructive
            and not (capability.financial and capability.external_side_effect),
            financial=capability.financial,
            external_side_effect=capability.external_side_effect,
            data_destructive=capability.data_destructive,
            privacy_impact=capability.privacy_impact,
            reasons=tuple(reasons),
        )
