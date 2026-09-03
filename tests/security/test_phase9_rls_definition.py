"""Static Phase 9 RLS inspection; live behavior remains a staging requirement."""

from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2] / "backend" / "migrations" / "versions" / "0009_realtime_voice.py"
)
PGTAP = Path(__file__).parents[2] / "infrastructure" / "supabase" / "tests" / "phase9_rls.test.sql"


def test_phase9_voice_tables_are_forced_rls_and_backend_only() -> None:
    source = MIGRATION.read_text()
    for table in ("voice_sessions", "voice_turns"):
        assert table in source
    assert "ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in source
    assert "ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY" in source
    assert "REVOKE ALL ON TABLE public.{table} FROM anon, authenticated" in source
    assert "GRANT SELECT" not in source
    assert "CREATE POLICY" not in source


def test_phase9_pgtap_covers_backend_only_voice_authority() -> None:
    source = PGTAP.read_text()
    assert "select plan(12)" in source
    assert "Voice sessions have RLS enabled" in source
    assert "Voice sessions force RLS" in source
    assert "Voice turns have RLS enabled" in source
    assert "Voice turns force RLS" in source
    assert "Authenticated role cannot directly read voice sessions" in source
    assert "Authenticated role cannot mutate voice session authority" in source
    assert "Authenticated role cannot inject a voice turn" in source
    assert "Authenticated role cannot rewrite voice turn outcomes" in source
