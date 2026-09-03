-- Phase 9 pgTAP validation for an authorized disposable Supabase staging database.
-- Apply Alembic head first. Voice session rows are backend-only and expose no
-- credential, provider, model, or turn metadata through direct client SQL.
begin;
select plan(12);

select ok(
  (select relrowsecurity from pg_class where oid = 'public.voice_sessions'::regclass),
  'Voice sessions have RLS enabled');
select ok(
  (select relforcerowsecurity from pg_class where oid = 'public.voice_sessions'::regclass),
  'Voice sessions force RLS');
select ok(
  (select relrowsecurity from pg_class where oid = 'public.voice_turns'::regclass),
  'Voice turns have RLS enabled');
select ok(
  (select relforcerowsecurity from pg_class where oid = 'public.voice_turns'::regclass),
  'Voice turns force RLS');

select ok(not has_table_privilege('anon', 'public.voice_sessions', 'SELECT'),
  'Anonymous role cannot read voice sessions');
select ok(not has_table_privilege('authenticated', 'public.voice_sessions', 'SELECT'),
  'Authenticated role cannot directly read voice sessions');
select ok(not has_table_privilege('authenticated', 'public.voice_sessions', 'INSERT'),
  'Authenticated role cannot create voice sessions');
select ok(not has_table_privilege('authenticated', 'public.voice_sessions', 'UPDATE'),
  'Authenticated role cannot mutate voice session authority');
select ok(not has_table_privilege('authenticated', 'public.voice_sessions', 'DELETE'),
  'Authenticated role cannot delete voice sessions');

select ok(not has_table_privilege('authenticated', 'public.voice_turns', 'SELECT'),
  'Authenticated role cannot directly read voice turns');
select ok(not has_table_privilege('authenticated', 'public.voice_turns', 'INSERT'),
  'Authenticated role cannot inject a voice turn');
select ok(not has_table_privilege('authenticated', 'public.voice_turns', 'UPDATE'),
  'Authenticated role cannot rewrite voice turn outcomes');

select * from finish();
rollback;
