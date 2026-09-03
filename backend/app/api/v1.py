"""Versioned API router for identity, authority, audit, tasks, and memory."""

from fastapi import APIRouter

from backend.app.audit.api import router as audit_router
from backend.app.identity.api import router as identity_router
from backend.app.memory.api import router as memory_router
from backend.app.orchestrator.api import router as orchestrator_router
from backend.app.permissions.api import router as permissions_router
from backend.app.tasks.api import router as tasks_router
from backend.app.text_assistant.api import router as text_assistant_router
from backend.app.voice.api import router as voice_router

router = APIRouter(prefix="/api/v1")
router.include_router(identity_router)
router.include_router(permissions_router)
router.include_router(audit_router)
router.include_router(tasks_router)
router.include_router(memory_router)
router.include_router(orchestrator_router)
router.include_router(text_assistant_router)
router.include_router(voice_router)
