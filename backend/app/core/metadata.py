"""Shared bounded, secret-redacted JSON metadata handling."""

import json
from typing import cast

from backend.app.core.redaction import redact_secrets


def _validate_json_shape(
    value: object,
    *,
    max_depth: int,
    max_nodes: int,
) -> None:
    """Reject deeply nested or structurally abusive JSON before recursive redaction."""
    nodes = 0
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > max_nodes:
            raise ValueError("Metadata has too many nested values")
        if depth > max_depth:
            raise ValueError("Metadata nesting is too deep")
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError("Metadata keys must be strings")
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, (list, tuple)):
            pending.extend((child, depth + 1) for child in item)
        elif item is not None and not isinstance(item, (str, int, float, bool)):
            raise ValueError("Metadata must contain only JSON-compatible values")


def sanitize_metadata(
    value: dict[str, object],
    *,
    max_bytes: int,
    max_entries: int = 32,
    max_depth: int = 5,
    max_nodes: int = 128,
) -> dict[str, object]:
    """Return redacted JSON metadata or reject an oversized/non-JSON payload."""
    if len(value) > max_entries:
        raise ValueError("Metadata has too many entries")
    _validate_json_shape(value, max_depth=max_depth, max_nodes=max_nodes)
    sanitized = cast(dict[str, object], redact_secrets(value))
    try:
        encoded = json.dumps(
            sanitized, separators=(",", ":"), sort_keys=True, ensure_ascii=True
        ).encode()
    except (TypeError, ValueError):
        raise ValueError("Metadata must be JSON-compatible") from None
    if len(encoded) > max_bytes:
        raise ValueError("Metadata exceeds the bounded limit")
    return sanitized
