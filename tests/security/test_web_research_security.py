"""Adversarial SSRF, redirect, DNS, response-bound, and injection tests."""

import asyncio
from collections.abc import Iterable

import pytest

from backend.app.research.enums import ResearchErrorCode
from backend.app.research.errors import ResearchError
from backend.app.research.fetch import RawFetchResponse, SafeFetcher
from backend.app.research.policy import ResearchBudget
from backend.app.research.url_safety import ResolvedTarget, URLSafetyPolicy


class Resolver:
    def __init__(self, outcomes: Iterable[tuple[str, ...]]) -> None:
        self.outcomes = tuple(outcomes)
        self.index = 0

    def resolve(self, host: str, port: int) -> tuple[str, ...]:
        del host, port
        outcome = self.outcomes[min(self.index, len(self.outcomes) - 1)]
        self.index += 1
        return outcome


class Transport:
    def __init__(self, responses: Iterable[RawFetchResponse]) -> None:
        self.responses = tuple(responses)
        self.targets: list[ResolvedTarget] = []

    async def request(
        self, target: ResolvedTarget, *, max_bytes: int, timeout: float
    ) -> RawFetchResponse:
        del max_bytes, timeout
        self.targets.append(target)
        return self.responses[len(self.targets) - 1]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://Example.COM", "https://example.com/"),
        ("https://example.com/a/../b", "https://example.com/b"),
        ("https://example.com/a/?b=2&a=1", "https://example.com/a/?a=1&b=2"),
        ("https://example.com/a#fragment", "https://example.com/a"),
        ("https://example.com/?utm_source=x&a=1", "https://example.com/?a=1"),
        ("http://example.com/a", "http://example.com/a"),
        ("https://example.com:443/a", "https://example.com/a"),
        ("http://example.com:80/a", "http://example.com/a"),
    ],
)
def test_public_urls_are_canonicalized(raw: str, expected: str) -> None:
    assert URLSafetyPolicy.canonicalize(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "file:///etc/passwd",
        "ftp://example.com/a",
        "gopher://example.com/a",
        "javascript:alert(1)",
        "data:text/plain,hello",
        "mailto:user@example.com",
        "https://user@example.com/a",
        "https://user:pass@example.com/a",
        "https://localhost/a",
        "https://api.localhost/a",
        "https://service.local/a",
        "https://metadata.google.internal/a",
        "https://printer.lan/a",
        "https://singlelabel/a",
        "https://2130706433/a",
        "https://example.com:22/a",
        "http://example.com:443/a",
        "https://example.com:80/a",
        "https:///missing-host",
        "https://example.com/\x00bad",
        "https://[::1]/a",
        "https://example.com:99999/a",
        "//example.com/a",
        "HTTPSX://example.com/a",
        "https://user%40example.com@127.0.0.1/a",
    ],
)
def test_ambiguous_or_dangerous_urls_are_blocked(raw: str) -> None:
    with pytest.raises(ResearchError) as caught:
        URLSafetyPolicy.canonicalize(raw)
    assert caught.value.code is ResearchErrorCode.BLOCKED_URL


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "127.1.2.3",
        "10.0.0.1",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",
        "0.0.0.0",  # noqa: S104 - adversarial resolver input, not a bind address
        "100.64.0.1",
        "192.0.2.1",
        "198.51.100.1",
        "203.0.113.1",
        "224.0.0.1",
        "255.255.255.255",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "2001:db8::1",
    ],
)
def test_non_global_dns_answers_are_blocked(address: str) -> None:
    policy = URLSafetyPolicy(Resolver(((address,),)))  # type: ignore[arg-type]
    with pytest.raises(ResearchError) as caught:
        policy.resolve_target("https://example.com/a")
    assert caught.value.code is ResearchErrorCode.BLOCKED_URL


def test_mixed_public_and_private_dns_answers_fail_closed() -> None:
    policy = URLSafetyPolicy(Resolver((("93.184.216.34", "127.0.0.1"),)))  # type: ignore[arg-type]
    with pytest.raises(ResearchError):
        policy.resolve_target("https://example.com/a")


def test_dns_rebinding_is_detected_across_redirect_resolution() -> None:
    policy = URLSafetyPolicy(
        Resolver((("93.184.216.34",), ("93.184.216.35",)))  # type: ignore[arg-type]
    )
    history: dict[str, tuple[str, ...]] = {}
    policy.resolve_target("https://example.com/a", resolution_history=history)
    with pytest.raises(ResearchError) as caught:
        policy.resolve_target("https://example.com/b", resolution_history=history)
    assert caught.value.code is ResearchErrorCode.DNS_REBINDING


def test_redirect_target_is_revalidated_before_second_request() -> None:
    resolver = Resolver((("93.184.216.34",), ("127.0.0.1",)))
    transport = Transport(
        (
            RawFetchResponse(302, {"location": "https://private.example/a"}, b""),
            RawFetchResponse(200, {"content-type": "text/plain"}, b"secret"),
        )
    )
    fetcher = SafeFetcher(URLSafetyPolicy(resolver), transport=transport)  # type: ignore[arg-type]
    with pytest.raises(ResearchError):
        asyncio.run(fetcher.fetch("https://example.com/a"))
    assert len(transport.targets) == 1


def test_redirect_limit_is_enforced() -> None:
    resolver = Resolver((("93.184.216.34",),) * 5)
    responses = tuple(
        RawFetchResponse(302, {"location": f"https://e{index}.example/a"}, b"")
        for index in range(5)
    )
    transport = Transport(responses)
    budget = ResearchBudget(max_redirects=2)
    fetcher = SafeFetcher(URLSafetyPolicy(resolver), transport=transport, budget=budget)  # type: ignore[arg-type]
    with pytest.raises(ResearchError):
        asyncio.run(fetcher.fetch("https://example.com/a"))
    assert len(transport.targets) == 3


@pytest.mark.parametrize(
    ("headers", "body", "code"),
    [
        ({"content-type": "application/json"}, b"{}", ResearchErrorCode.UNSUPPORTED_CONTENT),
        ({"content-type": "image/png"}, b"png", ResearchErrorCode.UNSUPPORTED_CONTENT),
        (
            {"content-type": "text/plain", "content-encoding": "gzip"},
            b"x",
            ResearchErrorCode.UNSUPPORTED_CONTENT,
        ),
        (
            {"content-type": "text/html", "content-encoding": "br"},
            b"x",
            ResearchErrorCode.UNSUPPORTED_CONTENT,
        ),
    ],
)
def test_unsupported_or_compressed_responses_are_rejected(
    headers: dict[str, str], body: bytes, code: ResearchErrorCode
) -> None:
    fetcher = SafeFetcher(
        URLSafetyPolicy(Resolver((("93.184.216.34",),))),  # type: ignore[arg-type]
        transport=Transport((RawFetchResponse(200, headers, body),)),
    )
    with pytest.raises(ResearchError) as caught:
        asyncio.run(fetcher.fetch("https://example.com/a"))
    assert caught.value.code is code


@pytest.mark.parametrize(
    "status,code",
    [
        (429, ResearchErrorCode.RATE_LIMITED),
        (404, ResearchErrorCode.PROVIDER_UNAVAILABLE),
        (500, ResearchErrorCode.PROVIDER_UNAVAILABLE),
    ],
)
def test_remote_failures_are_safely_classified(status: int, code: ResearchErrorCode) -> None:
    fetcher = SafeFetcher(
        URLSafetyPolicy(Resolver((("93.184.216.34",),))),  # type: ignore[arg-type]
        transport=Transport(
            (RawFetchResponse(status, {"content-type": "text/plain"}, b"raw provider secret"),)
        ),
    )
    with pytest.raises(ResearchError) as caught:
        asyncio.run(fetcher.fetch("https://example.com/a"))
    assert caught.value.code is code
    assert "raw provider secret" not in str(caught.value)


def test_success_uses_validated_pinned_ip_and_no_hidden_dns() -> None:
    transport = Transport(
        (RawFetchResponse(200, {"content-type": "text/plain"}, b"Public evidence"),)
    )
    fetcher = SafeFetcher(
        URLSafetyPolicy(Resolver((("93.184.216.34",),))),  # type: ignore[arg-type]
        transport=transport,
    )
    final_url, content_type, body = asyncio.run(fetcher.fetch("https://example.com/a"))
    assert final_url == "https://example.com/a"
    assert content_type == "text/plain"
    assert body == b"Public evidence"
    assert transport.targets[0].pinned_ip == "93.184.216.34"
