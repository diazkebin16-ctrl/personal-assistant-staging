"""Static Phase 7 RLS inspection; live behavior remains a staging requirement."""

from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2] / "backend" / "migrations" / "versions" / "0008_text_assistant.py"
)
PGTAP = Path(__file__).parents[2] / "infrastructure" / "supabase" / "tests" / "phase7_rls.test.sql"


def test_phase7_rls_is_owner_read_and_backend_write_only() -> None:
    source = MIGRATION.read_text()
    for table in ("conversations", "conversation_messages"):
        assert table in source
    assert "ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in source
    assert "REVOKE ALL ON TABLE public.{table} FROM anon, authenticated" in source
    assert "GRANT SELECT ON TABLE public.{table} TO authenticated" in source
    assert "conversations_select_own" in source
    assert "conversation_messages_select_own" in source
    assert "owner.auth_user_id = (SELECT auth.uid())" in source
    assert "FOR INSERT TO authenticated" not in source
    assert "FOR UPDATE TO authenticated" not in source


def test_phase7_pgtap_covers_isolation_and_direct_mutation_denial() -> None:
    source = PGTAP.read_text()
    assert "Owner conversation isolation" in source
    assert "Owner message isolation" in source
    assert "Client cannot insert conversation directly" in source
    assert "Client cannot forge conversation version" in source
    assert "Client cannot insert message directly" in source
    assert "Client cannot delete conversation history directly" in source
