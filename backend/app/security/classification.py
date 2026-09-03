"""Canonical data-sensitivity vocabulary shared by protected domains."""

from enum import StrEnum


class DataSensitivity(StrEnum):
    """Increasing data-sensitivity classes; classification never grants authority."""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    PRIVATE = "PRIVATE"
    SENSITIVE = "SENSITIVE"
    CRITICAL = "CRITICAL"


_SENSITIVITY_RANK = {
    DataSensitivity.PUBLIC: 0,
    DataSensitivity.INTERNAL: 1,
    DataSensitivity.PRIVATE: 2,
    DataSensitivity.SENSITIVE: 3,
    DataSensitivity.CRITICAL: 4,
}


def sensitivity_rank(value: DataSensitivity) -> int:
    """Return the canonical monotonic rank without changing persisted enum values."""
    return _SENSITIVITY_RANK[value]


def highest_sensitivity(*values: DataSensitivity) -> DataSensitivity:
    """Return the most restrictive classification and fail on an empty input."""
    if not values:
        raise ValueError("At least one sensitivity classification is required")
    return max(values, key=sensitivity_rank)


def classify_text_sensitivity(value: str) -> DataSensitivity:
    """Conservative server-owned text classifier; callers cannot lower its result."""
    normalized = value.casefold()
    critical_markers = (
        "-----begin private key-----",
        "service_role_key",
        "access_token",
        "refresh_token",
        "authorization: bearer",
    )
    if any(marker in normalized for marker in critical_markers):
        return DataSensitivity.CRITICAL
    sensitive_markers = ("password=", "api_key", "secret=", "credential")
    if any(marker in normalized for marker in sensitive_markers):
        return DataSensitivity.SENSITIVE
    return DataSensitivity.PRIVATE
