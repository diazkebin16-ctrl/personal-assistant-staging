-- Phase 7 pgTAP validation for an authorized disposable Supabase staging database.
-- Apply Alembic head first. Local inspection is not runtime RLS certification.
begin;
select plan(6);

insert into auth.users (id, email) values
 ('81111111-1111-1111-1111-111111111111','phase7-owner@example.invalid'),
 ('82222222-2222-2222-2222-222222222222','phase7-other@example.invalid');
insert into public.users (id, auth_user_id, display_name, status) values
 ('8aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','81111111-1111-1111-1111-111111111111','Owner','ACTIVE'),
 ('8bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','82222222-2222-2222-2222-222222222222','Other','ACTIVE');
insert into public.conversations (id,user_id,title,version,next_sequence) values
 ('80000000-0000-4000-8000-000000000011','8aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','Owner conversation',1,2),
 ('80000000-0000-4000-8000-000000000012','8bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','Other conversation',1,2);
insert into public.conversation_messages
 (id,conversation_id,user_id,role,status,sequence,content,sensitivity,idempotency_key,request_fingerprint)
values
 ('80000000-0000-4000-8000-000000000021','80000000-0000-4000-8000-000000000011','8aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','USER','COMPLETED',1,'owner text','PRIVATE','owner-message',repeat('a',64)),
 ('80000000-0000-4000-8000-000000000022','80000000-0000-4000-8000-000000000012','8bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','USER','COMPLETED',1,'other text','PRIVATE','other-message',repeat('b',64));

set local role authenticated;
set local request.jwt.claims =
 '{"sub":"81111111-1111-1111-1111-111111111111","role":"authenticated"}';
select results_eq($$select id from public.conversations order by id$$,
 array['80000000-0000-4000-8000-000000000011'::uuid], 'Owner conversation isolation');
select results_eq($$select id from public.conversation_messages order by id$$,
 array['80000000-0000-4000-8000-000000000021'::uuid], 'Owner message isolation');
select throws_ok($$insert into public.conversations (id,user_id,version,next_sequence)
 values (gen_random_uuid(),'8aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',1,1)$$,
 '42501',null,'Client cannot insert conversation directly');
select throws_ok($$update public.conversations set version=999$$,
 '42501',null,'Client cannot forge conversation version');
select throws_ok($$insert into public.conversation_messages
 (id,conversation_id,user_id,role,status,sequence,content,sensitivity,idempotency_key,request_fingerprint)
 values (gen_random_uuid(),'80000000-0000-4000-8000-000000000011',
 '8aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','USER','COMPLETED',2,'forged','PRIVATE','forged',repeat('c',64))$$,
 '42501',null,'Client cannot insert message directly');
select throws_ok($$delete from public.conversation_messages$$,
 '42501',null,'Client cannot delete conversation history directly');
select * from finish();
rollback;

