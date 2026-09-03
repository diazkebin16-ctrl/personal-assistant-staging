"""Static RLS definition checks; PostgreSQL runtime remains a staging gate."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = PROJECT_ROOT / "backend/migrations/versions/0001_identity_auth.py"
STAGING_TEST = PROJECT_ROOT / "infrastructure/supabase/tests/phase1_rls.test.sql"


def test_migration_defines_owner_scoped_read_only_rls_for_all_phase1_tables() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")

    for table in ("users", "devices", "auth_sessions"):
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in migration
        assert f"REVOKE ALL ON TABLE public.{table} FROM anon, authenticated" in migration
        assert f"GRANT SELECT ON TABLE public.{table} TO authenticated" in migration

    assert migration.count("CREATE POLICY") == 3
    assert "(SELECT auth.uid()) IS NOT NULL" in migration
    assert "GRANT INSERT" not in migration
    assert "GRANT UPDATE" not in migration
    assert "GRANT DELETE" not in migration


def test_staging_rls_suite_covers_cross_user_crud_boundaries() -> None:
    sql = STAGING_TEST.read_text(encoding="utf-8")

    assert "User A can SELECT only its own" in sql
    assert "cannot INSERT" in sql
    assert "cannot UPDATE" in sql
    assert "cannot DELETE" in sql
    assert "rollback;" in sql.lower()
