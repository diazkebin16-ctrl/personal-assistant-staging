"""Deterministic risk classification tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.app.identity.context import AuthenticationLevel, IdentityContext
from backend.app.permissions.enums import RiskLevel
from backend.app.permissions.models import Capability
from backend.app.permissions.risk import RiskEngine
from backend.app.permissions.schemas import PermissionScope


def identity() -> IdentityContext:
    return IdentityContext(
        user_id=uuid4(),
        auth_user_id=uuid4(),
        device_id=None,
        session_id=None,
        display_name="Risk Test",
        authentication_level=AuthenticationLevel.AAL2,
        token_expiry=datetime.now(UTC) + timedelta(hours=1),
    )


@pytest.mark.parametrize(
    ("key", "base", "external", "financial", "destructive", "privacy", "expected"),
    [
        ("settings.read", 0, False, False, False, False, RiskLevel.NEGLIGIBLE),
        ("profile.read", 0, False, False, False, True, RiskLevel.MODERATE),
        ("notification.send", 1, True, False, False, True, RiskLevel.ELEVATED),
        ("data.delete", 1, False, False, True, True, RiskLevel.HIGH),
        ("finance.execute", 0, True, True, False, True, RiskLevel.CRITICAL),
    ],
)
def test_server_owned_rules_apply_deterministic_risk_floors(
    key: str,
    base: int,
    external: bool,
    financial: bool,
    destructive: bool,
    privacy: bool,
    expected: RiskLevel,
) -> None:
    capability = Capability(
        key=key,
        name="Test",
        description="Risk test capability",
        category="test",
        default_risk_level=base,
        allowed_actions=["read"],
        external_side_effect=external,
        financial=financial,
        data_destructive=destructive,
        privacy_impact=privacy,
    )

    result = RiskEngine().evaluate(
        capability=capability,
        action="read",
        scope=PermissionScope(resource_type="test", operations=["read"]),
        identity=identity(),
        context={"risk_level": 0},
    )

    assert result.risk_level is expected


def test_risk_engine_rejects_action_outside_capability_vocabulary() -> None:
    capability = Capability(
        key="device.read",
        name="Read devices",
        description="Read owned device metadata",
        category="device",
        default_risk_level=RiskLevel.LOW,
        allowed_actions=["read"],
    )

    with pytest.raises(ValueError, match="server-owned capability vocabulary"):
        RiskEngine().evaluate(
            capability=capability,
            action="delete",
            scope=PermissionScope(resource_type="device", operations=["delete"]),
            identity=identity(),
            context={},
        )
