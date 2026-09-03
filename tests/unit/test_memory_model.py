"""Memory classification, bounds, provenance, and canonicalization tests."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from backend.app.memory.enums import MemoryClass, MemorySourceType
from backend.app.memory.schemas import (
    MemoryCreateRequest,
    MemoryProposal,
    memory_fingerprint,
)


@pytest.mark.parametrize("memory_class", list(MemoryClass))
def test_all_canonical_memory_classes_validate(memory_class: MemoryClass) -> None:
    expires_at = (
        datetime.now(UTC) + timedelta(minutes=5)
        if memory_class is MemoryClass.TEMPORARY_CONTEXT
        else None
    )
    request = MemoryCreateRequest(
        memory_class=memory_class,
        content="Meaningful bounded memory",
        expires_at=expires_at,
    )
    assert request.memory_class is memory_class


def test_temporary_context_requires_aware_expiration() -> None:
    with pytest.raises(ValidationError):
        MemoryCreateRequest(memory_class=MemoryClass.TEMPORARY_CONTEXT, content="temporary")
    with pytest.raises(ValidationError):
        MemoryCreateRequest(
            memory_class=MemoryClass.TEMPORARY_CONTEXT,
            content="temporary",
            expires_at=datetime.now(),
        )


def test_internal_provenance_and_confidence_are_bounded() -> None:
    with pytest.raises(ValidationError):
        MemoryProposal(
            memory_class=MemoryClass.OPERATIONAL,
            content="task state",
            source_type=MemorySourceType.TASK,
            confidence=101,
        )
    with pytest.raises(ValidationError):
        MemoryProposal(
            memory_class=MemoryClass.OPERATIONAL,
            content="device state",
            source_type=MemorySourceType.DEVICE,
            confidence=80,
        )


def test_fingerprint_is_deterministic_for_unicode_and_whitespace_normalization() -> None:
    first = memory_fingerprint(
        MemoryClass.PERSISTENT_PREFERENCE,
        "I prefer café  responses",
        "Style",
    )
    second = memory_fingerprint(
        MemoryClass.PERSISTENT_PREFERENCE,
        "  I PREFER cafe\u0301 responses ",
        "style",
    )
    assert first == second


def test_metadata_is_redacted_and_nested_abuse_is_rejected() -> None:
    request = MemoryCreateRequest(
        memory_class=MemoryClass.OPERATIONAL,
        content="Safe content",
        metadata={"access_token": "must-not-leak", "label": "safe"},
    )
    assert request.metadata["access_token"] == "***REDACTED***"  # noqa: S105
    abusive: object = "leaf"
    for _ in range(7):
        abusive = {"nested": abusive}
    with pytest.raises(ValidationError):
        MemoryCreateRequest(
            memory_class=MemoryClass.OPERATIONAL,
            content="Safe content",
            metadata=abusive,  # type: ignore[arg-type]
        )
