"""Static RLS evidence for Phase 6; live Supabase execution remains staging work."""

from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2] / "backend" / "migrations" / "versions" / "0007_orchestrator.py"
).read_text(encoding="utf-8")


def test_all_orchestrator_tables_enable_rls_and_revoke_direct_writes() -> None:
    for table in (
        "orchestration_workflows",
        "orchestration_plans",
        "orchestration_steps",
        "authorized_action_envelopes",
    ):
        assert "ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in MIGRATION or (
            "ENABLE ROW LEVEL SECURITY" in MIGRATION and table in MIGRATION
        )
        assert "REVOKE ALL ON TABLE public.{table} FROM anon, authenticated" in MIGRATION


def test_owner_policies_anchor_to_verified_auth_uid() -> None:
    assert "owner.auth_user_id = (SELECT auth.uid())" in MIGRATION
    assert "orchestration_workflows_select_own" in MIGRATION
    assert "orchestration_plans_select_own" in MIGRATION
    assert "orchestration_steps_select_own" in MIGRATION
    assert "authorized_action_envelopes_select_own" in MIGRATION


def test_no_authenticated_mutation_grant_or_policy_exists() -> None:
    assert "GRANT SELECT ON TABLE public.{table} TO authenticated" in MIGRATION
    assert "GRANT INSERT" not in MIGRATION
    assert "GRANT UPDATE" not in MIGRATION
    assert "GRANT DELETE" not in MIGRATION
    assert "FOR UPDATE TO authenticated" not in MIGRATION
    assert "FOR DELETE TO authenticated" not in MIGRATION
