-- Phase 3 pgTAP validation for an authorized disposable Supabase staging database.
-- Apply Alembic head first. This file is not a claim of local runtime validation.

begin;

select plan(7);

insert into auth.users (id, email)
values
    ('41111111-1111-1111-1111-111111111111', 'phase3-owner@example.invalid'),
    ('42222222-2222-2222-2222-222222222222', 'phase3-other@example.invalid');

insert into public.users (id, auth_user_id, display_name, status)
values
    ('4aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '41111111-1111-1111-1111-111111111111', 'Owner', 'ACTIVE'),
    ('4bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', '42222222-2222-2222-2222-222222222222', 'Other', 'ACTIVE');

insert into public.authorization_decisions (
    id, user_id, capability_key, action, scope, scope_digest, decision,
    reason_codes, risk_level, confirmation_required, scope_match, financial_guard_triggered
)
values
    (
        '40000000-0000-4000-8000-000000000001',
        '4aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'device.read', 'read',
        '{"resource_type":"device","resource_ids":[],"operations":["read"]}',
        repeat('a', 64), 'ALLOW', '["AUTHORIZED"]', 1, false, true, false
    ),
    (
        '40000000-0000-4000-8000-000000000002',
        '4bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'device.read', 'read',
        '{"resource_type":"device","resource_ids":[],"operations":["read"]}',
        repeat('b', 64), 'ALLOW', '["AUTHORIZED"]', 1, false, true, false
    );

insert into public.tasks (
    id, user_id, capability_key, action, scope, scope_digest, status, priority,
    idempotency_key, request_fingerprint, authorization_decision_id, metadata, result_metadata
)
values
    (
        '40000000-0000-4000-8000-000000000011',
        '4aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'device.read', 'read',
        '{"resource_type":"device","resource_ids":[],"operations":["read"]}',
        repeat('a', 64), 'QUEUED', 'NORMAL', 'phase3-owner-key', repeat('1', 64),
        '40000000-0000-4000-8000-000000000001', '{}', '{}'
    ),
    (
        '40000000-0000-4000-8000-000000000012',
        '4bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'device.read', 'read',
        '{"resource_type":"device","resource_ids":[],"operations":["read"]}',
        repeat('b', 64), 'RUNNING', 'NORMAL', 'phase3-other-key', repeat('2', 64),
        '40000000-0000-4000-8000-000000000002', '{}', '{}'
    );

insert into public.task_attempts (
    id, task_id, attempt_number, status, worker_id, execution_id, metadata
)
values (
    '40000000-0000-4000-8000-000000000021',
    '40000000-0000-4000-8000-000000000012', 1, 'RUNNING', 'staging-worker',
    '40000000-0000-4000-8000-000000000022', '{}'
);

insert into public.task_events (
    id, task_id, user_id, event_type, to_state, reason_code, actor_type, metadata
)
values (
    '40000000-0000-4000-8000-000000000031',
    '40000000-0000-4000-8000-000000000012',
    '4bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'CREATED', 'RUNNING',
    'CREATED_AUTHORIZED', 'SYSTEM', '{}'
);

set local role authenticated;
set local request.jwt.claims =
    '{"sub":"41111111-1111-1111-1111-111111111111","role":"authenticated"}';

select results_eq(
    $$select id from public.tasks order by id$$,
    array['40000000-0000-4000-8000-000000000011'::uuid],
    'User A can SELECT only its own tasks'
);

select is_empty(
    $$select * from public.task_attempts
      where task_id = '40000000-0000-4000-8000-000000000012'::uuid$$,
    'User A cannot SELECT User B attempts'
);

select is_empty(
    $$select * from public.task_events
      where user_id = '4bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'::uuid$$,
    'User A cannot SELECT User B events'
);

select throws_ok(
    $$update public.tasks set status = 'COMPLETED'
      where id = '40000000-0000-4000-8000-000000000011'::uuid$$,
    '42501', null, 'Authenticated client cannot directly change even its own task state'
);

select throws_ok(
    $$insert into public.task_attempts (
        id, task_id, attempt_number, status, worker_id, execution_id, metadata
      ) values (
        gen_random_uuid(), '40000000-0000-4000-8000-000000000011', 1, 'RUNNING',
        'spoofed-worker', gen_random_uuid(), '{}'
      )$$,
    '42501', null, 'Authenticated client cannot create execution attempts'
);

select throws_ok(
    $$delete from public.task_events
      where id = '40000000-0000-4000-8000-000000000031'::uuid$$,
    '42501', null, 'Authenticated client cannot tamper with TaskEvent history'
);

select results_eq(
    $$select count(*)::bigint from public.tasks$$,
    array[1::bigint],
    'Denied writes preserve visible owner task state'
);

select * from finish();
rollback;
