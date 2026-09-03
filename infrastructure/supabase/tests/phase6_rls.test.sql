-- Phase 6 pgTAP validation for an authorized disposable Supabase staging database.
-- Apply Alembic head first. Local inspection is not runtime RLS certification.
begin;
select plan(8);

insert into auth.users (id, email) values
 ('71111111-1111-1111-1111-111111111111','phase6-owner@example.invalid'),
 ('72222222-2222-2222-2222-222222222222','phase6-other@example.invalid');
insert into public.users (id, auth_user_id, display_name, status) values
 ('7aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','71111111-1111-1111-1111-111111111111','Owner','ACTIVE'),
 ('7bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','72222222-2222-2222-2222-222222222222','Other','ACTIVE');
insert into public.orchestration_workflows
 (id,user_id,intent_category,state,safe_mode,idempotency_key,request_fingerprint,intent_metadata,version)
values
 ('70000000-0000-4000-8000-000000000011','7aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','INFORMATIONAL','COMPLETED_NO_ACTION','NORMAL','phase6-owner-key',repeat('a',64),'{}',1),
 ('70000000-0000-4000-8000-000000000012','7bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','INFORMATIONAL','COMPLETED_NO_ACTION','NORMAL','phase6-other-key',repeat('b',64),'{}',1);
insert into public.orchestration_plans (id,workflow_id,fingerprint,plan_payload) values
 ('70000000-0000-4000-8000-000000000021','70000000-0000-4000-8000-000000000011',repeat('c',64),'{"summary":"safe","actions":[]}'),
 ('70000000-0000-4000-8000-000000000022','70000000-0000-4000-8000-000000000012',repeat('d',64),'{"summary":"safe","actions":[]}');
insert into public.orchestration_steps
 (id,workflow_id,user_id,step_type,to_state,reason_code,actor_type,metadata) values
 ('70000000-0000-4000-8000-000000000031','70000000-0000-4000-8000-000000000011','7aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','RECEIVED','RECEIVED','REQUEST_RECEIVED','USER','{}'),
 ('70000000-0000-4000-8000-000000000032','70000000-0000-4000-8000-000000000012','7bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','RECEIVED','RECEIVED','REQUEST_RECEIVED','USER','{}');

set local role authenticated;
set local request.jwt.claims =
 '{"sub":"71111111-1111-1111-1111-111111111111","role":"authenticated"}';
select results_eq($$select id from public.orchestration_workflows order by id$$,
 array['70000000-0000-4000-8000-000000000011'::uuid], 'Owner workflow isolation');
select results_eq($$select id from public.orchestration_plans order by id$$,
 array['70000000-0000-4000-8000-000000000021'::uuid], 'Owner plan isolation');
select results_eq($$select id from public.orchestration_steps order by id$$,
 array['70000000-0000-4000-8000-000000000031'::uuid], 'Owner step isolation');
select results_eq($$select count(*)::bigint from public.authorized_action_envelopes$$,
 array[0::bigint], 'Owner envelope isolation');
select throws_ok($$update public.orchestration_workflows set state='READY_FOR_EXECUTION'$$,
 '42501',null,'Client cannot force state');
select throws_ok($$update public.orchestration_plans set plan_payload='{}'$$,
 '42501',null,'Client cannot mutate plan');
select throws_ok($$delete from public.orchestration_steps$$,
 '42501',null,'Client cannot delete evidence');
select throws_ok($$insert into public.authorized_action_envelopes
 (id,workflow_id,user_id,task_id,capability_key,action,arguments,scope_digest,
 plan_fingerprint,permission_id,authorization_decision_id,risk_level,safe_mode,
 policy_version,idempotency_key) values
 (gen_random_uuid(),'70000000-0000-4000-8000-000000000011',
 '7aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',gen_random_uuid(),'finance.execute','transfer',
 '{}',repeat('e',64),repeat('f',64),gen_random_uuid(),gen_random_uuid(),0,'NORMAL',
 'forged','forged-envelope')$$,'42501',null,'Client cannot forge envelope');
select * from finish();
rollback;
