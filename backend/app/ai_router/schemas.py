"""Immutable domain contracts for deterministic AI routing and provider calls."""

from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.app.ai_router.enums import (
    Complexity,
    FailureCategory,
    LatencyTier,
    ModelCapability,
    ModelClass,
    ProviderHealth,
    QualityTier,
    RoutingOutcome,
    RoutingReason,
)
from backend.app.security.classification import DataSensitivity, highest_sensitivity

CatalogKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=2,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    ),
]


class PricingMetadata(BaseModel):
    """Versioned operational price metadata expressed as currency microunits."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] = "USD"
    input_microunits_per_million_tokens: int = Field(ge=0)
    output_microunits_per_million_tokens: int = Field(ge=0)
    pricing_version: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    effective_date: date

    def estimate_microunits(self, input_tokens: int, output_tokens: int) -> int:
        """Return a deterministic ceiling estimate, never an actual billed amount."""
        input_cost = input_tokens * self.input_microunits_per_million_tokens
        output_cost = output_tokens * self.output_microunits_per_million_tokens
        return (input_cost + output_cost + 999_999) // 1_000_000


class ProviderDefinition(BaseModel):
    """Server-owned privacy and availability boundary for a provider adapter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: CatalogKey
    enabled: bool = False
    local: bool = False
    max_sensitivity: DataSensitivity = DataSensitivity.PUBLIC
    private_data_approved: bool = False
    sensitive_data_approved: bool = False
    critical_data_approved: bool = False

    @model_validator(mode="after")
    def validate_approval_chain(self) -> "ProviderDefinition":
        if self.critical_data_approved and (not self.local or not self.sensitive_data_approved):
            raise ValueError("Critical-data approval requires a local, sensitive-approved provider")
        if self.sensitive_data_approved and not self.private_data_approved:
            raise ValueError("Sensitive-data approval requires private-data approval")
        return self


class ModelDefinition(BaseModel):
    """Immutable catalog description; clients cannot introduce model identifiers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_key: CatalogKey
    model_id: CatalogKey
    model_class: ModelClass
    enabled: bool = False
    routing_enabled: bool = True
    evaluation_enabled: bool = False
    capabilities: frozenset[ModelCapability]
    context_limit: int = Field(ge=1, le=2_000_000)
    output_limit: int = Field(ge=1, le=131_072)
    max_sensitivity: DataSensitivity = DataSensitivity.PUBLIC
    quality_tier: QualityTier
    latency_tier: LatencyTier
    pricing: PricingMetadata
    deprecated: bool = False
    fallback_priority: int = Field(default=100, ge=0, le=10_000)

    @model_validator(mode="after")
    def validate_model_capabilities(self) -> "ModelDefinition":
        if self.output_limit > self.context_limit:
            raise ValueError("Model output limit cannot exceed its context limit")
        if self.model_class is ModelClass.REALTIME and (
            ModelCapability.AUDIO_REALTIME not in self.capabilities
        ):
            raise ValueError("Realtime models must declare audio/realtime capability")
        if self.model_class is ModelClass.EMBEDDING and (
            ModelCapability.EMBEDDINGS not in self.capabilities
        ):
            raise ValueError("Embedding models must declare embedding capability")
        if self.enabled and not self.routing_enabled and not self.evaluation_enabled:
            raise ValueError("Enabled models must be routable or explicitly evaluation-enabled")
        return self


class ModelReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_key: CatalogKey
    model_id: CatalogKey
    model_class: ModelClass
    quality_tier: QualityTier

    @classmethod
    def from_definition(cls, model: ModelDefinition) -> "ModelReference":
        return cls(
            provider_key=model.provider_key,
            model_id=model.model_id,
            model_class=model.model_class,
            quality_tier=model.quality_tier,
        )


class RoutingRequest(BaseModel):
    """Internal authoritative routing input; it intentionally contains no raw context."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_type: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=128,
            pattern=r"^[a-z][a-z0-9._-]*$",
        ),
    ]
    task_id: UUID | None = None
    complexity: Complexity
    required_capabilities: frozenset[ModelCapability] = Field(default_factory=frozenset)
    sensitivity: DataSensitivity
    context_sensitivities: tuple[DataSensitivity, ...] = Field(default=(), max_length=256)
    estimated_input_tokens: int = Field(ge=0, le=2_000_000)
    requested_output_tokens: int = Field(ge=1, le=65_536)
    realtime_required: bool = False
    embedding_required: bool = False
    structured_output_required: bool = False
    tool_calling_required: bool = False
    local_only: bool = False

    @property
    def effective_sensitivity(self) -> DataSensitivity:
        return highest_sensitivity(self.sensitivity, *self.context_sensitivities)

    @property
    def effective_capabilities(self) -> frozenset[ModelCapability]:
        capabilities = set(self.required_capabilities)
        if self.embedding_required:
            capabilities.add(ModelCapability.EMBEDDINGS)
        elif self.realtime_required:
            capabilities.add(ModelCapability.AUDIO_REALTIME)
        else:
            capabilities.add(ModelCapability.TEXT_GENERATION)
        if self.structured_output_required:
            capabilities.add(ModelCapability.STRUCTURED_OUTPUT)
        if self.tool_calling_required:
            capabilities.add(ModelCapability.TOOL_CALLING)
        return frozenset(capabilities)

    @model_validator(mode="after")
    def validate_specialized_requirements(self) -> "RoutingRequest":
        if self.realtime_required and self.embedding_required:
            raise ValueError("A routing request cannot be realtime and embedding simultaneously")
        if self.embedding_required and (
            self.structured_output_required or self.tool_calling_required
        ):
            raise ValueError("Embedding requests cannot require generation-only capabilities")
        return self


class RoutingDecision(BaseModel):
    """Immutable result for one routing attempt, including explicit denials."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    task_id: UUID | None = None
    outcome: RoutingOutcome
    selected_model: ModelReference | None
    reason_codes: tuple[RoutingReason, ...]
    policy_version: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    required_capabilities: tuple[ModelCapability, ...]
    effective_sensitivity: DataSensitivity
    fallback_chain: tuple[ModelReference, ...] = ()
    estimated_cost_microunits: int | None = Field(default=None, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_outcome(self) -> "RoutingDecision":
        if self.outcome is RoutingOutcome.SELECTED and self.selected_model is None:
            raise ValueError("Selected routing decisions require a model")
        if self.outcome is RoutingOutcome.DENIED and self.selected_model is not None:
            raise ValueError("Denied routing decisions cannot select a model")
        if not self.reason_codes:
            raise ValueError("Routing decisions require at least one reason code")
        return self


class ProviderRequest(BaseModel):
    """Ephemeral provider input; raw content is never persisted or logged by the Router."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_text: str = Field(min_length=1, max_length=500_000, repr=False)
    output_token_budget: int = Field(ge=1, le=65_536)
    structured_output_required: bool = False
    tool_calling_required: bool = False


class ProviderResponse(BaseModel):
    """Provider-neutral response metadata plus ephemeral output content."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    output_text: str = Field(max_length=1_000_000, repr=False)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    actual_cost_microunits: int | None = Field(default=None, ge=0)


class ProviderAttemptFailure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model: ModelReference
    category: FailureCategory
    retryable: bool


class AIExecutionResult(BaseModel):
    """Successful bounded provider execution with recorded fallback chronology."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    routing_decision: RoutingDecision
    final_model: ModelReference
    response: ProviderResponse
    failures: tuple[ProviderAttemptFailure, ...] = ()


class ProviderHealthSnapshot:
    """Immutable per-routing health input supplied by trusted runtime monitoring."""

    __slots__ = ("_statuses",)

    def __init__(self, statuses: dict[str, ProviderHealth] | None = None) -> None:
        self._statuses = dict(statuses or {})

    def status_for(self, provider_key: str) -> ProviderHealth:
        return self._statuses.get(provider_key, ProviderHealth.AVAILABLE)
