"""Small, extensible safeguards against accidental secret disclosure."""

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "***REDACTED***"
SENSITIVE_KEY_FRAGMENTS = (
    "access_token",
    "refresh_token",
    "password",
    "token",
    "jwt",
    "api_key",
    "authorization",
    "secret",
    "service_role",
    "private_key",
)

_KEY_VALUE_PATTERN = re.compile(
    r"(?i)([\"']?(?:access[_-]?token|refresh[_-]?token|password|token|jwt|api[_-]?key|authorization|secret|service[_-]?role(?:[_-]?key)?|private[_-]?key)[\"']?\s*[:=]\s*)([\"']?)([^\"'\s,}\]]+)(\2)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


def is_sensitive_key(key: object) -> bool:
    """Return whether a mapping key is conventionally secret-bearing."""
    normalized = str(key).lower().replace("-", "_")
    collapsed = normalized.replace("_", "")
    return any(fragment.replace("_", "") in collapsed for fragment in SENSITIVE_KEY_FRAGMENTS)


def redact_text(value: str) -> str:
    """Redact common key/value and bearer-token patterns from text."""
    redacted = _KEY_VALUE_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}{match.group(4)}",
        value,
    )
    return _BEARER_PATTERN.sub(f"Bearer {REDACTED}", redacted)


def redact_secrets(value: Any) -> Any:
    """Recursively redact sensitive mapping values without mutating the input."""
    if isinstance(value, Mapping):
        return {
            key: REDACTED if is_sensitive_key(key) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
