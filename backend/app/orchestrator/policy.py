"""Pure server-owned Orchestrator policy for quality, sensitivity, and safe modes."""

from dataclasses import dataclass

from backend.app.ai_router.enums import Complexity
from backend.app.memory.schemas import MemoryContextPack
from backend.app.orchestrator.enums import IntentCategory, SafeMode
from backend.app.security.classification import (
    DataSensitivity,
    classify_text_sensitivity,
    highest_sensitivity,
)

POLICY_VERSION = "orchestrator-v1"


@dataclass(frozen=True, slots=True)
class OrchestratorFeatures:
    ai_enabled: bool = True
    action_workflows_enabled: bool = True


class OrchestratorPolicy:
    """Deterministic policy. Feature flags can restrict but never grant authority."""

    def __init__(
        self,
        *,
        safe_mode: SafeMode = SafeMode.NORMAL,
        features: OrchestratorFeatures | None = None,
    ) -> None:
        self.safe_mode = safe_mode
        self.features = features or OrchestratorFeatures()

    def permits_intent(self, category: IntentCategory) -> bool:
        if self.safe_mode is SafeMode.MAINTENANCE:
            return False
        if category is IntentCategory.UNSUPPORTED:
            return False
        if category in {IntentCategory.ACTION, IntentCategory.DESTRUCTIVE}:
            return (
                self.safe_mode is SafeMode.NORMAL
                and self.features.ai_enabled
                and self.features.action_workflows_enabled
            )
        return self.features.ai_enabled

    def permits_execution_readiness(self) -> bool:
        return self.safe_mode is SafeMode.NORMAL and self.features.action_workflows_enabled

    @staticmethod
    def complexity(category: IntentCategory, input_length: int) -> Complexity:
        if category is IntentCategory.DESTRUCTIVE:
            return Complexity.HIGH
        if category is IntentCategory.ACTION:
            return Complexity.HIGH if input_length > 4000 else Complexity.MEDIUM
        if input_length <= 500:
            return Complexity.LOW
        if input_length <= 4000:
            return Complexity.MEDIUM
        return Complexity.HIGH

    @staticmethod
    def context_sensitivity(
        pack: MemoryContextPack | None, input_text: str | None = None
    ) -> DataSensitivity:
        """Server-classified user input and Memory can only raise sensitivity."""
        values = [classify_text_sensitivity(input_text) if input_text else DataSensitivity.PRIVATE]
        if pack is not None:
            groups = (
                pack.persistent_preferences,
                pack.operational_context,
                pack.historical_decisions,
                pack.temporary_context,
            )
            values.extend(item.sensitivity for group in groups for item in group)
        return highest_sensitivity(*values)
