"""Small request builders shared by Phase 2 matrix tests."""

from datetime import datetime
from typing import Any
from uuid import UUID


def scope(
    resource_type: str,
    operation: str,
    resource_ids: list[str] | None = None,
    *,
    additional_operations: list[str] | None = None,
) -> dict[str, object]:
    return {
        "resource_type": resource_type,
        "resource_ids": resource_ids or [],
        "operations": [operation, *(additional_operations or [])],
    }


def grant_payload(
    capability_key: str,
    permission_scope: dict[str, object],
    *,
    policy: str = "NEVER",
    auto_execute: bool = False,
    device_id: UUID | str | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "capability_key": capability_key,
        "scope": permission_scope,
        "confirmation_policy": policy,
        "auto_execute": auto_execute,
        "reason": "Explicit test user grant",
    }
    if device_id is not None:
        payload["device_id"] = str(device_id)
    if expires_at is not None:
        payload["expires_at"] = expires_at.isoformat()
    return payload


def proposal(
    capability_key: str,
    action: str,
    requested_scope: dict[str, object],
    *,
    confirmation_id: UUID | str | None = None,
    context: dict[str, object] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "capability_key": capability_key,
        "action": action,
        "scope": requested_scope,
        "context": context or {},
    }
    if confirmation_id is not None:
        payload["confirmation_id"] = str(confirmation_id)
    return payload
