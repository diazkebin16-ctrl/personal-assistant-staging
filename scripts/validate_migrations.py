"""Deterministically validate Alembic upgrade, downgrade, and re-upgrade."""

import sqlite3
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHASE2_TABLES = {
    "capabilities",
    "permissions",
    "authorization_decisions",
    "confirmation_requests",
    "audit_events",
}
PHASE3_TABLES = {"tasks", "task_attempts", "task_events"}
PHASE4_TABLES = {"memory_records", "memory_revisions", "memory_events"}
PHASE5_TABLES = {"ai_routing_decisions", "ai_usage_records"}
PHASE6_TABLES = {
    "orchestration_workflows",
    "orchestration_plans",
    "orchestration_steps",
    "authorized_action_envelopes",
}
PHASE7_TABLES = {"conversations", "conversation_messages"}
PHASE9_TABLES = {"voice_sessions", "voice_turns"}
REQUIRED_TABLES = {
    "users",
    "devices",
    "auth_sessions",
    "alembic_version",
    *PHASE2_TABLES,
    *PHASE3_TABLES,
    *PHASE4_TABLES,
    *PHASE5_TABLES,
    *PHASE6_TABLES,
    *PHASE7_TABLES,
    *PHASE9_TABLES,
}
PHASE1_TABLES = {"users", "devices", "auth_sessions"}


def _tables(database_path: Path) -> set[str]:
    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        return {str(row[0]) for row in rows}
    finally:
        connection.close()


def _columns(database_path: Path, table: str) -> set[str]:
    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        return {str(row[1]) for row in rows}
    finally:
        connection.close()


def validate_migrations() -> None:
    """Require clean-base upgrade, safe downgrade, and deterministic re-upgrade."""
    with tempfile.TemporaryDirectory(prefix="personal-assistant-migrations-") as directory:
        database_path = Path(directory) / "migration-validation.db"
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")

        command.upgrade(config, "head")
        if not REQUIRED_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Migration upgrade did not create the expected tables")
        if "allowed_actions" not in _columns(database_path, "capabilities"):
            raise RuntimeError("Capability action migration did not reach HEAD")
        if not {"version", "request_fingerprint", "authorization_decision_id"}.issubset(
            _columns(database_path, "tasks")
        ):
            raise RuntimeError("Task Engine migration did not reach HEAD")
        if not {"version", "fingerprint", "deduplication_key", "sensitivity"}.issubset(
            _columns(database_path, "memory_records")
        ):
            raise RuntimeError("Memory Core migration did not reach HEAD")
        if not {
            "outcome",
            "provider_key",
            "model_id",
            "effective_sensitivity",
            "estimated_cost_microunits",
        }.issubset(_columns(database_path, "ai_routing_decisions")):
            raise RuntimeError("AI Router decision migration did not reach HEAD")
        if not {
            "routing_decision_id",
            "input_tokens",
            "output_tokens",
            "failure_category",
            "actual_cost_microunits",
        }.issubset(_columns(database_path, "ai_usage_records")):
            raise RuntimeError("AI Router usage migration did not reach HEAD")
        command.check(config)

        command.downgrade(config, "0008_text_assistant")
        if PHASE9_TABLES.intersection(_tables(database_path)):
            raise RuntimeError("Phase 9 downgrade left Realtime Voice tables behind")
        if not PHASE7_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Phase 9 downgrade damaged Phase 7 tables")
        command.upgrade(config, "head")
        if not PHASE9_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Phase 9 re-upgrade was not deterministic")

        command.downgrade(config, "0007_orchestrator")
        if PHASE7_TABLES.intersection(_tables(database_path)):
            raise RuntimeError("Phase 7 downgrade left Text Assistant tables behind")
        if not PHASE6_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Phase 7 downgrade damaged Phase 6 tables")
        command.upgrade(config, "head")
        if not PHASE7_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Phase 7 re-upgrade was not deterministic")

        command.downgrade(config, "0006_ai_router")
        if PHASE6_TABLES.intersection(_tables(database_path)):
            raise RuntimeError("Phase 6 downgrade left Orchestrator tables behind")
        if not PHASE5_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Phase 6 downgrade damaged Phase 5 tables")
        command.upgrade(config, "head")
        if not PHASE6_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Phase 6 re-upgrade was not deterministic")

        command.downgrade(config, "0005_memory_core")
        if PHASE5_TABLES.intersection(_tables(database_path)):
            raise RuntimeError("Phase 5 downgrade left AI Router tables behind")
        if not PHASE4_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Phase 5 downgrade damaged Phase 4 tables")

        command.upgrade(config, "head")
        if not PHASE5_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Phase 5 re-upgrade was not deterministic")

        command.downgrade(config, "0004_task_engine")
        if PHASE4_TABLES.intersection(_tables(database_path)):
            raise RuntimeError("Phase 4 downgrade left Memory Core tables behind")
        if not PHASE3_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Phase 4 downgrade damaged Phase 3 tables")

        command.upgrade(config, "head")
        if not PHASE4_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Phase 4 re-upgrade was not deterministic")

        command.downgrade(config, "0003_capability_actions")
        if PHASE3_TABLES.intersection(_tables(database_path)):
            raise RuntimeError("Phase 3 downgrade left Task Engine tables behind")
        if not PHASE2_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Phase 3 downgrade damaged Phase 2 tables")

        command.upgrade(config, "head")
        if not PHASE3_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Phase 3 re-upgrade was not deterministic")

        command.downgrade(config, "0002_permissions_risk_audit")
        if not PHASE2_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Correction downgrade damaged Phase 2 tables")
        if "allowed_actions" in _columns(database_path, "capabilities"):
            raise RuntimeError("Correction downgrade left allowed_actions behind")

        command.upgrade(config, "head")
        if "allowed_actions" not in _columns(database_path, "capabilities"):
            raise RuntimeError("Correction re-upgrade was not deterministic")

        command.downgrade(config, "0001_identity_auth")
        current_tables = _tables(database_path)
        if PHASE2_TABLES.intersection(current_tables):
            raise RuntimeError("Phase 2 downgrade left Phase 2 tables behind")
        if not PHASE1_TABLES.issubset(current_tables):
            raise RuntimeError("Phase 2 downgrade damaged Phase 1 tables")

        command.upgrade(config, "head")
        if not REQUIRED_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Phase 2 re-upgrade was not deterministic")

        command.downgrade(config, "base")
        if PHASE1_TABLES.intersection(_tables(database_path)):
            raise RuntimeError("Migration downgrade left Phase 1 tables behind")

        command.upgrade(config, "head")
        if not REQUIRED_TABLES.issubset(_tables(database_path)):
            raise RuntimeError("Migration re-upgrade was not deterministic")


if __name__ == "__main__":
    validate_migrations()
