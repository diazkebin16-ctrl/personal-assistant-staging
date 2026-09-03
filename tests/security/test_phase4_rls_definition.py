"""Static validation of Phase 4 PostgreSQL RLS and staging evidence."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = PROJECT_ROOT / "backend/migrations/versions/0005_memory_core.py"
STAGING_TEST = PROJECT_ROOT / "infrastructure/supabase/tests/phase4_rls.test.sql"


def test_phase4_migration_defines_owner_reads_and_blocks_direct_mutation() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in ("memory_records", "memory_revisions", "memory_events"):
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"REVOKE ALL ON TABLE public.{table} FROM anon, authenticated" in sql
        assert f"GRANT SELECT ON TABLE public.{table} TO authenticated" in sql
    assert "GRANT INSERT" not in sql
    assert "GRANT UPDATE" not in sql
    assert "GRANT DELETE" not in sql
    assert "owner.auth_user_id = (SELECT auth.uid())" in sql
    assert "status != 'DELETED'" in sql


def test_phase4_staging_suite_covers_isolation_and_protected_mutations() -> None:
    sql = STAGING_TEST.read_text(encoding="utf-8")
    assert "User A can SELECT only its own memory rows" in sql
    assert "User A cannot SELECT User B memory revisions" in sql
    assert "User A cannot SELECT User B memory events" in sql
    assert "cannot alter protected memory ownership" in sql
    assert "cannot forge memory provenance or state" in sql
    assert "cannot bypass deterministic privacy deletion" in sql
    assert "cannot tamper with MemoryRevision history" in sql
    assert "cannot tamper with MemoryEvent history" in sql
    assert "select plan(8)" in sql
