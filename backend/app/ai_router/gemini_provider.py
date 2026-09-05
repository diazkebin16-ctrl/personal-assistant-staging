"""Google Gemini text adapter for the provider-neutral AI Router."""

from __future__ import annotations

import asyncio
from typing import Any

from google import genai
from google.genai import errors, types

from backend.app.ai_router.enums import FailureCategory
from backend.app.ai_router.provider import ProviderFailure
from backend.app.ai_router.schemas import ProviderRequest, ProviderResponse


class GeminiProvider:
    """Bounded Gemini text provider; credentials remain server-side only."""

    key = "gemini"

    def __init__(self, api_key: str, *, client: Any | None = None) -> None:
        if not api_key.strip():
            raise ValueError("Gemini API key must not be empty")
        self._client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(api_version="v1"),
        )

    async def generate(
        self,
        model_id: str,
        request: ProviderRequest,
    ) -> ProviderResponse:
        if request.tool_calling_required or request.structured_output_required:
            raise ProviderFailure(FailureCategory.UNSUPPORTED_CAPABILITY)

        try:
            async with asyncio.timeout(30.0):
                response = await self._client.aio.models.generate_content(
                    model=model_id,
                    contents=request.input_text,
                    config=types.GenerateContentConfig(
                        max_output_tokens=request.output_token_budget,
                    ),
                )
        except TimeoutError:
            raise ProviderFailure(FailureCategory.TIMEOUT) from None
        except errors.APIError as exc:
            raise ProviderFailure(self._category_for_status(getattr(exc, "code", None))) from None

        try:
            output_text = response.text or ""
        except (AttributeError, ValueError):
            output_text = ""
        if not output_text:
            raise ProviderFailure(FailureCategory.MALFORMED_RESPONSE)

        usage = getattr(response, "usage_metadata", None)
        input_tokens = self._usage_int(usage, "prompt_token_count")
        candidate_tokens = self._usage_int(usage, "candidates_token_count")
        thought_tokens = self._usage_int(usage, "thoughts_token_count")
        cached_tokens = self._usage_int(usage, "cached_content_token_count")

        return ProviderResponse(
            output_text=output_text,
            input_tokens=input_tokens,
            output_tokens=candidate_tokens + thought_tokens,
            cached_tokens=cached_tokens,
            actual_cost_microunits=None,
        )

    @staticmethod
    def _usage_int(usage: object | None, field: str) -> int:
        if usage is None:
            return 0
        value = getattr(usage, field, 0)
        return int(value or 0)

    @staticmethod
    def _category_for_status(code: object) -> FailureCategory:
        if code in {401, 403}:
            return FailureCategory.AUTHENTICATION_ERROR
        if code in {408, 504}:
            return FailureCategory.TIMEOUT
        if code == 429:
            return FailureCategory.RATE_LIMITED
        if code in {400, 404, 409, 422}:
            return FailureCategory.INVALID_REQUEST
        if isinstance(code, int) and 500 <= code <= 599:
            return FailureCategory.INTERNAL_PROVIDER_ERROR
        if isinstance(code, int) and 400 <= code <= 499:
            return FailureCategory.INVALID_REQUEST
        return FailureCategory.PROVIDER_UNAVAILABLE
