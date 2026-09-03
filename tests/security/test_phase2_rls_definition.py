"""Static Phase 2 RLS checks; PostgreSQL runtime remains a staging gate."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = PROJECT_ROOT / "backend/migrations/versions/0002_permissions_risk_audit.py"
STAGING_TEST = PROJECT_ROOT / "infrastructure/supabase/tests/phase2_rls.test.sql"


def test_phase2_migration_defines_read_only_owner_rls() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE POLICY capabilities_select_enabled" in migration
    for table in (
        "permissions",
        "authorization_decisions",
        "confirmation_requests",
        "audit_events",
    ):
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in migration
        assert f"REVOKE ALL ON TABLE public.{table} FROM anon, authenticated" in migration
        assert f"GRANT SELECT ON TABLE public.{table} TO authenticated" in migration
        assert f"CREATE POLICY {table}_select_own" in migration

    assert "GRANT INSERT" not in migration
    assert "GRANT UPDATE" not in migration
    assert "GRANT DELETE" not in migration


def test_phase2_staging_suite_covers_owner_and_write_boundaries() -> None:
    sql = STAGING_TEST.read_text(encoding="utf-8")

    for phrase in (
        "User A can SELECT only its own permission",
        "User A cannot SELECT User B confirmation",
        "User A cannot SELECT User B audit",
        "cannot INSERT another user''s permission",
        "cannot UPDATE another user''s permission",
        "cannot APPROVE another user''s confirmation",
        "cannot DELETE another user''s audit",
    ):
        assert phrase in sql
    assert "rollback;" in sql.lower()
