"""OpenAI Responses API adapter for the provider-neutral AI Router."""

from __future__ import annotations

from typing import Any

import openai
from openai import AsyncOpenAI

from backend.app.ai_router.diagnostics import ProviderDiagnosticResponse, ProviderResponseStatus
from backend.app.ai_router.enums import FailureCategory
from backend.app.ai_router.provider import ProviderFailure
from backend.app.ai_router.schemas import ProviderRequest, ProviderResponse


class OpenAIProvider:
    """Bounded OpenAI text provider; credentials remain server-side only."""

    key = "openai"

    def __init__(self, api_key: str) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key must not be empty")
        self._client = AsyncOpenAI(api_key=api_key, timeout=30.0, max_retries=0)

    async def generate(
        self,
        model_id: str,
        request: ProviderRequest,
    ) -> ProviderResponse:
        """Generate text for normal routing while retaining the existing fail-closed contract."""
        diagnostic = await self.generate_for_evaluation(model_id, request)
        if diagnostic.status is not ProviderResponseStatus.COMPLETED:
            raise ProviderFailure(FailureCategory.MALFORMED_RESPONSE)
        return ProviderResponse(
            output_text=diagnostic.output_text,
            input_tokens=diagnostic.input_tokens,
            output_tokens=diagnostic.output_tokens,
            cached_tokens=diagnostic.cached_tokens,
            actual_cost_microunits=diagnostic.actual_cost_microunits,
        )

    async def generate_for_evaluation(
        self,
        model_id: str,
        request: ProviderRequest,
    ) -> ProviderDiagnosticResponse:
        """Preserve Responses metadata for explicit evaluation, including incomplete calls."""
        response = await self._create_response(model_id, request)
        return self._normalize_response(response)

    async def _create_response(self, model_id: str, request: ProviderRequest) -> Any:
        if request.tool_calling_required:
            raise ProviderFailure(FailureCategory.UNSUPPORTED_CAPABILITY)

        try:
            return await self._client.responses.create(
                model=model_id,
                input=request.input_text,
                max_output_tokens=request.output_token_budget,
            )
        except openai.AuthenticationError as exc:
            raise ProviderFailure(FailureCategory.AUTHENTICATION_ERROR) from exc
        except openai.RateLimitError as exc:
            raise ProviderFailure(FailureCategory.RATE_LIMITED) from exc
        except openai.APITimeoutError as exc:
            raise ProviderFailure(FailureCategory.TIMEOUT) from exc
        except openai.BadRequestError as exc:
            raise ProviderFailure(FailureCategory.INVALID_REQUEST) from exc
        except openai.APIConnectionError as exc:
            raise ProviderFailure(FailureCategory.PROVIDER_UNAVAILABLE) from exc
        except openai.InternalServerError as exc:
            raise ProviderFailure(FailureCategory.INTERNAL_PROVIDER_ERROR) from exc
        except openai.APIError as exc:
            raise ProviderFailure(FailureCategory.INTERNAL_PROVIDER_ERROR) from exc

    @staticmethod
    def _normalize_response(response: Any) -> ProviderDiagnosticResponse:
        """Normalize only structural metadata; never retain raw provider payloads."""
        output_text = str(getattr(response, "output_text", "") or "")
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0) if usage else 0
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0) if usage else 0

        cached_tokens = 0
        reasoning_tokens = 0
        if usage is not None:
            input_details = getattr(usage, "input_tokens_details", None)
            if input_details is not None:
                cached_tokens = int(getattr(input_details, "cached_tokens", 0) or 0)
            output_details = getattr(usage, "output_tokens_details", None)
            if output_details is not None:
                reasoning_tokens = int(getattr(output_details, "reasoning_tokens", 0) or 0)

        provider_status = str(getattr(response, "status", "") or "").casefold()
        incomplete_details = getattr(response, "incomplete_details", None)
        incomplete_reason = None
        if incomplete_details is not None:
            raw_reason = getattr(incomplete_details, "reason", None)
            if raw_reason is not None:
                incomplete_reason = str(raw_reason)[:128]

        if provider_status == "completed" and output_text:
            status = ProviderResponseStatus.COMPLETED
        elif provider_status == "incomplete":
            status = ProviderResponseStatus.INCOMPLETE
            incomplete_reason = incomplete_reason or "unknown"
        elif provider_status == "completed":
            status = ProviderResponseStatus.MALFORMED
        else:
            status = ProviderResponseStatus.PROVIDER_ERROR

        reported_model = getattr(response, "model", None)
        return ProviderDiagnosticResponse(
            status=status,
            output_text=output_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            reasoning_tokens=reasoning_tokens,
            incomplete_reason=incomplete_reason,
            reported_model_id=str(reported_model)[:128] if reported_model else None,
            actual_cost_microunits=None,
        )
