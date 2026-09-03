"""OpenAI Responses API adapter for the provider-neutral AI Router."""

from __future__ import annotations

import openai
from openai import AsyncOpenAI

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
        if request.tool_calling_required:
            raise ProviderFailure(FailureCategory.UNSUPPORTED_CAPABILITY)

        try:
            response = await self._client.responses.create(
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

        output_text = response.output_text or ""
        if not output_text:
            raise ProviderFailure(FailureCategory.MALFORMED_RESPONSE)

        usage = response.usage
        input_tokens = usage.input_tokens if usage is not None else 0
        output_tokens = usage.output_tokens if usage is not None else 0

        cached_tokens = 0
        if usage is not None:
            details = getattr(usage, "input_tokens_details", None)
            if details is not None:
                cached_tokens = int(getattr(details, "cached_tokens", 0) or 0)

        return ProviderResponse(
            output_text=output_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            actual_cost_microunits=None,
        )
