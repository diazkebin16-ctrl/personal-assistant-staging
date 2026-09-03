"""Static validation of Phase 3 PostgreSQL RLS and staging evidence."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = PROJECT_ROOT / "backend/migrations/versions/0004_task_engine.py"
STAGING_TEST = PROJECT_ROOT / "infrastructure/supabase/tests/phase3_rls.test.sql"


def test_phase3_migration_defines_owner_read_and_blocks_direct_mutation() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in ("tasks", "task_attempts", "task_events"):
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"REVOKE ALL ON TABLE public.{table} FROM anon, authenticated" in sql
        assert f"GRANT SELECT ON TABLE public.{table} TO authenticated" in sql
    assert "GRANT INSERT" not in sql
    assert "GRANT UPDATE" not in sql
    assert "GRANT DELETE" not in sql
    assert "owner.auth_user_id = (SELECT auth.uid())" in sql


def test_phase3_staging_suite_covers_cross_user_isolation_and_state_tampering() -> None:
    sql = STAGING_TEST.read_text(encoding="utf-8")
    assert "User A can SELECT only its own tasks" in sql
    assert "User A cannot SELECT User B attempts" in sql
    assert "User A cannot SELECT User B events" in sql
    assert "cannot directly change even its own task state" in sql
    assert "cannot create execution attempts" in sql
    assert "cannot tamper with TaskEvent history" in sql
    assert "select plan(7)" in sql
