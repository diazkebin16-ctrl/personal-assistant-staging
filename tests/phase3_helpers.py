"""Small request builders shared by Task Engine tests."""

from datetime import datetime
from typing import Any
from uuid import UUID


def task_payload(
    capability_key: str,
    action: str,
    task_scope: dict[str, object],
    idempotency_key: str,
    *,
    device_id: UUID | str | None = None,
    expires_at: datetime | None = None,
    priority: str = "NORMAL",
    max_retries: int = 0,
    metadata: dict[str, object] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "capability_key": capability_key,
        "action": action,
        "scope": task_scope,
        "idempotency_key": idempotency_key,
        "priority": priority,
        "max_retries": max_retries,
        "metadata": metadata or {},
    }
    if device_id is not None:
        payload["device_id"] = str(device_id)
    if expires_at is not None:
        payload["expires_at"] = expires_at.isoformat()
    return payload
