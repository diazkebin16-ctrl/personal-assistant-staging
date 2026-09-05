"""Gemini provider adapter normalization and privacy tests."""

import asyncio
from types import SimpleNamespace

import pytest
from google.genai import types

from backend.app.ai_router.enums import FailureCategory
from backend.app.ai_router.gemini_provider import GeminiProvider
from backend.app.ai_router.provider import ProviderFailure
from backend.app.ai_router.schemas import ProviderRequest


class _FakeModels:
    def __init__(self, *, response: object | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict[str, object] = {}

    async def generate_content(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("fake response was not configured")
        return self.response


class _FakeClient:
    def __init__(self, models: _FakeModels) -> None:
        self.aio = SimpleNamespace(models=models)


def test_gemini_provider_maps_text_usage_and_output_budget() -> None:
    usage = SimpleNamespace(
        prompt_token_count=7,
        candidates_token_count=3,
        thoughts_token_count=2,
        cached_content_token_count=1,
    )
    response = SimpleNamespace(text="GEMINI_OK", usage_metadata=usage)
    models = _FakeModels(response=response)
    provider = GeminiProvider("test-key", client=_FakeClient(models))
    request = ProviderRequest(input_text="Reply with exactly: GEMINI_OK", output_token_budget=8)

    result = asyncio.run(provider.generate("gemini-2.5-flash-lite", request))

    assert result.output_text == "GEMINI_OK"
    assert result.input_tokens == 7
    assert result.output_tokens == 5
    assert result.cached_tokens == 1
    assert result.actual_cost_microunits is None
    assert models.kwargs["model"] == "gemini-2.5-flash-lite"
    config = models.kwargs["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.max_output_tokens == 8


def test_gemini_provider_rejects_unimplemented_capabilities() -> None:
    provider = GeminiProvider(
        "test-key",
        client=_FakeClient(_FakeModels(response=SimpleNamespace(text="unused"))),
    )
    for request in (
        ProviderRequest(
            input_text="public",
            output_token_budget=8,
            structured_output_required=True,
        ),
        ProviderRequest(
            input_text="public",
            output_token_budget=8,
            tool_calling_required=True,
        ),
    ):
        with pytest.raises(ProviderFailure) as failure:
            asyncio.run(provider.generate("gemini-2.5-flash-lite", request))
        assert failure.value.category is FailureCategory.UNSUPPORTED_CAPABILITY


def test_gemini_provider_normalizes_timeout_without_leaking_content() -> None:
    content_marker = "prompt-marker-never-log"
    api_key = "key-marker-never-log"
    provider = GeminiProvider(
        api_key,
        client=_FakeClient(_FakeModels(error=TimeoutError(content_marker))),
    )
    request = ProviderRequest(input_text=content_marker, output_token_budget=8)

    with pytest.raises(ProviderFailure) as failure:
        asyncio.run(provider.generate("gemini-2.5-flash-lite", request))

    assert failure.value.category is FailureCategory.TIMEOUT
    assert content_marker not in str(failure.value)
    assert api_key not in str(failure.value)
    assert content_marker not in repr(request)
    assert api_key not in repr(provider)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, FailureCategory.AUTHENTICATION_ERROR),
        (403, FailureCategory.AUTHENTICATION_ERROR),
        (408, FailureCategory.TIMEOUT),
        (429, FailureCategory.RATE_LIMITED),
        (500, FailureCategory.INTERNAL_PROVIDER_ERROR),
        (503, FailureCategory.INTERNAL_PROVIDER_ERROR),
        (400, FailureCategory.INVALID_REQUEST),
        (404, FailureCategory.INVALID_REQUEST),
        (None, FailureCategory.PROVIDER_UNAVAILABLE),
    ],
)
def test_gemini_provider_normalizes_api_statuses(
    status: object,
    expected: FailureCategory,
) -> None:
    assert GeminiProvider._category_for_status(status) is expected


def test_gemini_provider_rejects_empty_or_missing_text() -> None:
    provider = GeminiProvider(
        "test-key",
        client=_FakeClient(_FakeModels(response=SimpleNamespace(text="", usage_metadata=None))),
    )
    with pytest.raises(ProviderFailure) as failure:
        asyncio.run(
            provider.generate(
                "gemini-2.5-flash-lite",
                ProviderRequest(input_text="public", output_token_budget=8),
            )
        )
    assert failure.value.category is FailureCategory.MALFORMED_RESPONSE
