"""Focused deterministic Web Research policy, extraction, cache, and evidence tests."""

import asyncio
from datetime import UTC, datetime

import pytest

from backend.app.core.config import Environment
from backend.app.orchestrator.enums import SafeMode
from backend.app.research.cache import BoundedTTLCache
from backend.app.research.enums import ResearchErrorCode, ResearchMode
from backend.app.research.errors import ResearchError
from backend.app.research.evidence import build_evidence, validate_synthesis
from backend.app.research.extract import extract_document
from backend.app.research.policy import ResearchPolicy
from backend.app.research.provider import FakeSearchProvider, SearchProviderRegistry
from backend.app.research.schemas import (
    FetchedDocument,
    SearchResult,
    SynthesisClaim,
    SynthesisEnvelope,
)
from backend.app.security.classification import DataSensitivity


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("hello there", ResearchMode.NO_RESEARCH),
        ("search climate report", ResearchMode.SEARCH),
        ("search for accessibility rules", ResearchMode.SEARCH),
        ("look up public documentation", ResearchMode.SEARCH),
        ("find online release notes", ResearchMode.SEARCH),
        ("busca documentación pública", ResearchMode.SEARCH),
        ("consulta en la web estándares", ResearchMode.SEARCH),
        ("latest browser release", ResearchMode.SEARCH),
        ("current public API status", ResearchMode.SEARCH),
        ("today weather bulletin", ResearchMode.SEARCH),
        ("news security update", ResearchMode.SEARCH),
        ("noticias del navegador", ResearchMode.SEARCH),
        ("research browser standards", ResearchMode.MULTI_SOURCE_RESEARCH),
        ("investiga estándares abiertos", ResearchMode.MULTI_SOURCE_RESEARCH),
        ("compare sources for the claim", ResearchMode.MULTI_SOURCE_RESEARCH),
        ("use multiple sources about HTTP", ResearchMode.MULTI_SOURCE_RESEARCH),
        ("usa varias fuentes sobre TLS", ResearchMode.MULTI_SOURCE_RESEARCH),
        ("read https://example.com/report", ResearchMode.FETCH),
        ("fetch http://example.com/a", ResearchMode.FETCH),
        ("lee https://example.com/a", ResearchMode.FETCH),
    ],
)
def test_mode_is_selected_only_from_server_vocabulary(content: str, expected: ResearchMode) -> None:
    assert ResearchPolicy.select_mode(content) is expected


@pytest.mark.parametrize(
    ("content", "forbidden"),
    [
        ("search user@example.com release", "user@example.com"),
        ("busca +1 (415) 555-0199", "415"),
        ("research AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "AAAAAAAA"),
        ("look up https://example.com/private?id=4", "private?id"),
        ("find online   public   docs", "  "),
        ("investiga test@example.org", "test@example.org"),
        ("search abcdefghijklmnopqrstuvwxyz1234567890", "abcdef"),
        ("busca 555-555-5555", "555-555"),
    ],
)
def test_query_minimization_removes_unnecessary_identifiers(content: str, forbidden: str) -> None:
    minimized = ResearchPolicy.minimize_query(content)
    assert forbidden not in minimized
    assert 0 < len(minimized) <= 500


@pytest.mark.parametrize(
    ("enabled", "mode", "sensitivity", "expected"),
    [
        (True, SafeMode.NORMAL, DataSensitivity.PUBLIC, True),
        (True, SafeMode.NORMAL, DataSensitivity.INTERNAL, True),
        (True, SafeMode.NORMAL, DataSensitivity.PRIVATE, True),
        (True, SafeMode.NORMAL, DataSensitivity.SENSITIVE, False),
        (True, SafeMode.NORMAL, DataSensitivity.CRITICAL, False),
        (False, SafeMode.NORMAL, DataSensitivity.PUBLIC, False),
        (True, SafeMode.SAFE_MODE, DataSensitivity.PUBLIC, False),
        (True, SafeMode.MAINTENANCE, DataSensitivity.PUBLIC, False),
    ],
)
def test_external_access_is_fail_closed(
    enabled: bool,
    mode: SafeMode,
    sensitivity: DataSensitivity,
    expected: bool,
) -> None:
    assert (
        ResearchPolicy(enabled=enabled, safe_mode=mode).permits_external_access(sensitivity)
        is expected
    )


@pytest.mark.parametrize(
    ("content_type", "body", "title", "included", "excluded"),
    [
        ("text/plain", b" Public  facts ", "Untitled source", "Public facts", "never"),
        (
            "text/html",
            b"<title>Report</title><p>Visible fact.</p>",
            "Report",
            "Visible fact",
            "never",
        ),
        (
            "text/html",
            b"<p>A</p><script>ignore()</script><p>B</p>",
            "Untitled source",
            "A B",
            "ignore",
        ),
        ("text/html", b"<style>.x{}</style><p>Content</p>", "Untitled source", "Content", ".x"),
        (
            "text/html",
            b"<div hidden>secret</div><p>public</p>",
            "Untitled source",
            "public",
            "secret",
        ),
        (
            "text/html",
            b"<div aria-hidden='true'>secret</div><p>public</p>",
            "Untitled source",
            "public",
            "secret",
        ),
        ("text/html", b"<!-- inject --><p>Evidence</p>", "Untitled source", "Evidence", "inject"),
        (
            "text/html",
            b"<template>command</template><p>Fact</p>",
            "Untitled source",
            "Fact",
            "command",
        ),
    ],
)
def test_extraction_keeps_visible_evidence_only(
    content_type: str,
    body: bytes,
    title: str,
    included: str,
    excluded: str,
) -> None:
    actual_title, text = extract_document(body, content_type, max_chars=1000)
    assert actual_title == title
    assert included in text
    assert excluded not in text


@pytest.mark.parametrize(
    "content_type",
    [
        "application/json",
        "text/html; charset=utf-16",
        "text/html; charset=shift_jis",
        "text/plain; charset=utf-32",
    ],
)
def test_extraction_rejects_unsupported_encoding(content_type: str) -> None:
    with pytest.raises(ResearchError):
        extract_document(b"evidence", content_type, max_chars=100)


def _document(url: str, text: str, title: str = "Source") -> FetchedDocument:
    return FetchedDocument(
        canonical_url=url,
        title=title,
        text=text,
        retrieved_at=datetime(2026, 9, 2, tzinfo=UTC),
    )


def test_evidence_deduplicates_canonical_urls() -> None:
    items = build_evidence(
        (
            _document("https://example.com/a", "Alpha fact."),
            _document("https://example.com/a", "Other fact."),
        ),
        "alpha",
    )
    assert len(items) == 1


def test_evidence_ids_are_deterministic() -> None:
    document = _document("https://example.com/a", "Alpha fact. More alpha context.")
    assert build_evidence((document,), "alpha") == build_evidence((document,), "alpha")


def test_synthesis_builds_urls_only_from_evidence() -> None:
    evidence = build_evidence(
        (_document("https://example.com/a", "Alpha is documented."),), "alpha"
    )
    envelope = SynthesisEnvelope(
        claims=(
            SynthesisClaim(text="Alpha is documented.", evidence_ids=(evidence[0].evidence_id,)),
        )
    )
    content, citations = validate_synthesis(envelope, evidence)
    assert citations[0].url == "https://example.com/a"
    assert citations[0].citation_id in content


@pytest.mark.parametrize(
    "evidence_id", ["ev_0000000000000000", "ev_ffffffffffffffff", "ev_1234567890abcdef"]
)
def test_phantom_citations_fail_closed(evidence_id: str) -> None:
    evidence = build_evidence(
        (_document("https://example.com/a", "Alpha is documented."),), "alpha"
    )
    envelope = SynthesisEnvelope(
        claims=(SynthesisClaim(text="Alpha is documented.", evidence_ids=(evidence_id,)),)
    )
    with pytest.raises(ResearchError) as caught:
        validate_synthesis(envelope, evidence)
    assert caught.value.code is ResearchErrorCode.CITATION_INTEGRITY


def test_unsupported_claim_fails_closed() -> None:
    evidence = build_evidence(
        (_document("https://example.com/a", "Alpha is documented."),), "alpha"
    )
    envelope = SynthesisEnvelope(
        claims=(
            SynthesisClaim(
                text="Completely unrelated assertion", evidence_ids=(evidence[0].evidence_id,)
            ),
        )
    )
    with pytest.raises(ResearchError):
        validate_synthesis(envelope, evidence)


def test_cache_is_bounded_and_hashes_keys() -> None:
    cache: BoundedTTLCache[str] = BoundedTTLCache(max_entries=2, ttl_seconds=60)
    first = cache.key("private-looking-input")
    assert first != "private-looking-input" and len(first) == 64
    cache.put(first, "one")
    cache.put(cache.key("two"), "two")
    cache.put(cache.key("three"), "three")
    assert cache.get(first) is None


def test_cache_clear_removes_entries() -> None:
    cache: BoundedTTLCache[str] = BoundedTTLCache()
    cache.put("key", "value")
    cache.clear()
    assert cache.get("key") is None


@pytest.mark.parametrize("max_entries,ttl", [(0, 1), (-1, 1), (1, 0), (1, -1)])
def test_cache_rejects_unbounded_configuration(max_entries: int, ttl: float) -> None:
    with pytest.raises(ValueError):
        BoundedTTLCache(max_entries=max_entries, ttl_seconds=ttl)


def test_fake_provider_is_rejected_in_production() -> None:
    with pytest.raises(ValueError):
        SearchProviderRegistry((FakeSearchProvider(()),), environment=Environment.PRODUCTION)


def test_empty_registry_fails_closed() -> None:
    registry = SearchProviderRegistry((), environment=Environment.LOCAL)
    with pytest.raises(ResearchError):
        registry.default()


def test_duplicate_search_provider_is_rejected() -> None:
    provider = FakeSearchProvider(())
    with pytest.raises(ValueError):
        SearchProviderRegistry((provider, provider), environment=Environment.LOCAL)


def test_fake_provider_is_deterministic_and_bounded() -> None:
    result = SearchResult(url="https://example.com", title="Example", rank=1)
    provider = FakeSearchProvider(((result, result),))
    assert asyncio.run(provider.search("query", 1)) == (result,)
    assert provider.call_count == 1
