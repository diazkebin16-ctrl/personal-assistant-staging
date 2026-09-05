"""Provider-neutral diagnostic metadata for explicit model evaluation only."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProviderResponseStatus(StrEnum):
    """Normalized provider response outcomes used by explicit evaluations."""

    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    MALFORMED = "malformed"
    PROVIDER_ERROR = "provider_error"


class ProviderDiagnosticResponse(BaseModel):
    """Privacy-safe provider response metadata retained for explicit evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ProviderResponseStatus
    output_text: str = Field(default="", max_length=1_000_000, repr=False)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    incomplete_reason: str | None = Field(default=None, max_length=128)
    reported_model_id: str | None = Field(default=None, max_length=128)
    actual_cost_microunits: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_usage_shape(self) -> "ProviderDiagnosticResponse":
        if self.cached_tokens > self.input_tokens:
            raise ValueError("Cached input tokens cannot exceed total input tokens")
        if self.reasoning_tokens > self.output_tokens:
            raise ValueError("Reasoning tokens cannot exceed total output tokens")
        if self.status is ProviderResponseStatus.INCOMPLETE and not self.incomplete_reason:
            raise ValueError("Incomplete responses require a normalized reason")
        if self.status is ProviderResponseStatus.COMPLETED and not self.output_text:
            raise ValueError("Completed responses require visible output text")
        return self
