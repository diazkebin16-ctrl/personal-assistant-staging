"""Small Memory API builders shared by Phase 4 tests."""

from datetime import datetime
from typing import Any
from uuid import UUID

from httpx import AsyncClient

from tests.helpers import bearer
from tests.phase2_helpers import grant_payload, scope


async def grant_memory_permissions(
    client: AsyncClient,
    token: str,
    *,
    delete_policy: str = "NEVER",
) -> None:
    grants = (
        grant_payload("memory.read", scope("memory", "read")),
        grant_payload(
            "memory.write",
            scope(
                "memory",
                "create",
                additional_operations=["archive", "update"],
            ),
        ),
        grant_payload(
            "memory.delete",
            scope("memory", "delete"),
            policy=delete_policy,
        ),
    )
    for grant in grants:
        response = await client.post("/api/v1/permissions/grant", headers=bearer(token), json=grant)
        assert response.status_code == 200


def memory_payload(
    content: str,
    *,
    memory_class: str = "PERSISTENT_PREFERENCE",
    subject: str | None = "interaction",
    summary: str | None = None,
    source_device_id: UUID | str | None = None,
    expires_at: datetime | None = None,
    importance: int = 70,
    sensitivity: str = "PRIVATE",
    metadata: dict[str, object] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "memory_class": memory_class,
        "content": content,
        "subject": subject,
        "importance": importance,
        "sensitivity": sensitivity,
        "metadata": metadata or {},
    }
    if summary is not None:
        payload["summary"] = summary
    if source_device_id is not None:
        payload["source_device_id"] = str(source_device_id)
    if expires_at is not None:
        payload["expires_at"] = expires_at.isoformat()
    return payload
