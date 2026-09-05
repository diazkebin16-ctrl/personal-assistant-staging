"""OpenAI Responses diagnostic normalization without live provider calls."""

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import httpx
import openai
import pytest

from backend.app.ai_router.diagnostics import ProviderResponseStatus
from backend.app.ai_router.enums import FailureCategory
from backend.app.ai_router.openai_provider import OpenAIProvider
from backend.app.ai_router.provider import ProviderFailure
from backend.app.ai_router.schemas import ProviderRequest


def _usage(
    *,
    input_tokens: int = 20,
    cached_tokens: int = 4,
    output_tokens: int = 8,
    reasoning_tokens: int = 2,
) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=input_tokens,
        input_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
        output_tokens=output_tokens,
        output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning_tokens),
    )


def _response(
    *,
    status: str,
    output_text: str = "",
    usage: SimpleNamespace | None = None,
    incomplete_reason: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        output_text=output_text,
        usage=usage,
        incomplete_details=(
            SimpleNamespace(reason=incomplete_reason) if incomplete_reason is not None else None
        ),
        model="gpt-5-nano-2026-08-07",
        output=(SimpleNamespace(type="reasoning"),) if not output_text else (),
    )


def test_completed_visible_output_preserves_usage_and_reported_model() -> None:
    result = OpenAIProvider._normalize_response(
        _response(status="completed", output_text="Hola", usage=_usage())
    )
    assert result.status is ProviderResponseStatus.COMPLETED
    assert result.output_text == "Hola"
    assert result.input_tokens == 20
    assert result.cached_tokens == 4
    assert result.output_tokens == 8
    assert result.reasoning_tokens == 2
    assert result.reported_model_id == "gpt-5-nano-2026-08-07"


def test_incomplete_max_output_tokens_is_not_malformed_and_preserves_usage() -> None:
    result = OpenAIProvider._normalize_response(
        _response(
            status="incomplete",
            usage=_usage(input_tokens=18, cached_tokens=0, output_tokens=128, reasoning_tokens=128),
            incomplete_reason="max_output_tokens",
        )
    )
    assert result.status is ProviderResponseStatus.INCOMPLETE
    assert result.incomplete_reason == "max_output_tokens"
    assert result.input_tokens == 18
    assert result.output_tokens == 128
    assert result.reasoning_tokens == 128
    assert result.output_text == ""


def test_completed_empty_output_is_truly_malformed_but_usage_is_retained() -> None:
    result = OpenAIProvider._normalize_response(
        _response(status="completed", usage=_usage(output_tokens=7, reasoning_tokens=7))
    )
    assert result.status is ProviderResponseStatus.MALFORMED
    assert result.output_tokens == 7
    assert result.reasoning_tokens == 7


def test_non_completed_non_incomplete_response_is_provider_error_with_usage() -> None:
    result = OpenAIProvider._normalize_response(
        _response(status="failed", usage=_usage(output_tokens=3, reasoning_tokens=1))
    )
    assert result.status is ProviderResponseStatus.PROVIDER_ERROR
    assert result.output_tokens == 3


def test_normal_generate_remains_fail_closed_for_incomplete_response() -> None:
    async def scenario() -> None:
        provider = OpenAIProvider("test-only-key")

        class Responses:
            async def create(self, **_: Any) -> SimpleNamespace:
                return _response(
                    status="incomplete",
                    usage=_usage(output_tokens=128, reasoning_tokens=128),
                    incomplete_reason="max_output_tokens",
                )

        cast(Any, provider)._client = SimpleNamespace(responses=Responses())
        with pytest.raises(ProviderFailure) as failure:
            await provider.generate(
                "gpt-5-nano",
                ProviderRequest(input_text="public fixture", output_token_budget=128),
            )
        assert failure.value.category is FailureCategory.MALFORMED_RESPONSE

    asyncio.run(scenario())


def test_api_timeout_is_normalized_once_without_retry() -> None:
    async def scenario() -> None:
        provider = OpenAIProvider("test-only-key")

        class Responses:
            def __init__(self) -> None:
                self.calls = 0

            async def create(self, **_: Any) -> SimpleNamespace:
                self.calls += 1
                request = httpx.Request("POST", "https://api.openai.com/v1/responses")
                raise openai.APITimeoutError(request=request)

        responses = Responses()
        cast(Any, provider)._client = SimpleNamespace(responses=responses)
        with pytest.raises(ProviderFailure) as failure:
            await provider.generate_for_evaluation(
                "gpt-5-nano",
                ProviderRequest(input_text="public fixture", output_token_budget=256),
            )
        assert failure.value.category is FailureCategory.TIMEOUT
        assert responses.calls == 1

    asyncio.run(scenario())


def test_provider_does_not_log_prompt_or_key(caplog: pytest.LogCaptureFixture) -> None:
    async def scenario() -> None:
        credential = "benchmark-key-not-real"
        private_text = "sensitive-fixture-that-must-not-be-logged"
        provider = OpenAIProvider(credential)

        class Responses:
            async def create(self, **_: Any) -> SimpleNamespace:
                return _response(status="completed", output_text="ok", usage=_usage())

        cast(Any, provider)._client = SimpleNamespace(responses=Responses())
        await provider.generate_for_evaluation(
            "gpt-5-nano",
            ProviderRequest(input_text=private_text, output_token_budget=256),
        )
        rendered = caplog.text
        assert credential not in rendered
        assert private_text not in rendered

    asyncio.run(scenario())
