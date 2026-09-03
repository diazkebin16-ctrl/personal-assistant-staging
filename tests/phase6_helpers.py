"""Deterministic Phase 6 composition fixtures with no network or real model provider."""

import json
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai_router.policy import AIRoutingPolicy
from backend.app.ai_router.provider import FakeProvider, ProviderRegistry
from backend.app.ai_router.schemas import ProviderResponse
from backend.app.ai_router.service import AIRouter
from backend.app.audit.engine import AuditEngine
from backend.app.identity.context import IdentityContext
from backend.app.identity.models import User
from backend.app.memory.service import MemoryService
from backend.app.orchestrator.enums import SafeMode, SideEffectClass
from backend.app.orchestrator.policy import OrchestratorFeatures, OrchestratorPolicy
from backend.app.orchestrator.service import OrchestratorService
from backend.app.permissions.engine import PermissionsEngine
from backend.app.permissions.enums import ConfirmationPolicy
from backend.app.permissions.models import Permission
from backend.app.permissions.schemas import PermissionGrantRequest, PermissionScope
from backend.app.permissions.service import PermissionAdministrationService
from backend.app.tasks.service import TaskService
from tests.phase5_helpers import routing_catalog


async def add_identity_user(session: AsyncSession, identity: IdentityContext) -> None:
    session.add(
        User(
            id=identity.user_id,
            auth_user_id=identity.auth_user_id,
            display_name=identity.display_name,
        )
    )
    await session.flush()


def provider_response(output_text: str) -> ProviderResponse:
    return ProviderResponse(
        output_text=output_text,
        input_tokens=100,
        output_tokens=max(1, len(output_text) // 4),
    )


def candidate_plan(
    capability_key: str,
    action: str,
    *,
    resource_type: str,
    resource_ids: list[str] | None = None,
    arguments: dict[str, object] | None = None,
    side_effect: SideEffectClass = SideEffectClass.READ_ONLY,
) -> str:
    return json.dumps(
        {
            "summary": "Validated candidate action",
            "actions": [
                {
                    "capability_key": capability_key,
                    "action": action,
                    "scope": {
                        "resource_type": resource_type,
                        "resource_ids": resource_ids or [],
                        "operations": [action],
                    },
                    "arguments": arguments or {},
                    "side_effect_class": side_effect.value,
                }
            ],
        }
    )


def build_orchestrator(
    session: AsyncSession,
    outcomes: Iterable[ProviderResponse],
    *,
    safe_mode: SafeMode = SafeMode.NORMAL,
    ai_enabled: bool = True,
    actions_enabled: bool = True,
) -> tuple[OrchestratorService, dict[str, FakeProvider]]:
    audit = AuditEngine(session)
    permissions = PermissionsEngine(session, audit)
    memory = MemoryService(session, permissions, audit)
    tasks = TaskService(session, permissions, audit)
    catalog = routing_catalog()
    response_items = tuple(outcomes)
    providers = {
        key: FakeProvider(key, response_items)
        for key in ("primary", "equivalent", "sensitive-approved", "local-approved")
    }
    router = AIRouter(
        session,
        catalog,
        AIRoutingPolicy(catalog),
        providers=ProviderRegistry(providers.values()),
    )
    policy = OrchestratorPolicy(
        safe_mode=safe_mode,
        features=OrchestratorFeatures(
            ai_enabled=ai_enabled,
            action_workflows_enabled=actions_enabled,
        ),
    )
    return (
        OrchestratorService(session, memory, router, tasks, audit, policy),
        providers,
    )


async def grant(
    session: AsyncSession,
    identity: IdentityContext,
    capability_key: str,
    action: str,
    resource_type: str,
    *,
    confirmation_policy: ConfirmationPolicy = ConfirmationPolicy.NEVER,
) -> Permission:
    admin = PermissionAdministrationService(session, AuditEngine(session))
    permission, _ = await admin.grant(
        identity,
        PermissionGrantRequest(
            capability_key=capability_key,
            scope=PermissionScope(
                resource_type=resource_type,
                operations=[action],
            ),
            confirmation_policy=confirmation_policy,
        ),
    )
    return permission
