-- Phase 2 pgTAP validation for a disposable Supabase staging database.
-- Apply Alembic head first. This file is not a claim of local runtime validation.

begin;

select plan(8);

insert into auth.users (id, email)
values
    ('31111111-1111-1111-1111-111111111111', 'phase2-owner@example.invalid'),
    ('32222222-2222-2222-2222-222222222222', 'phase2-other@example.invalid');

insert into public.users (id, auth_user_id, display_name, status)
values
    ('3aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '31111111-1111-1111-1111-111111111111', 'Owner', 'ACTIVE'),
    ('3bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', '32222222-2222-2222-2222-222222222222', 'Other', 'ACTIVE');

insert into public.permissions (
    id, user_id, capability_id, scope, scope_digest, status,
    confirmation_policy, auto_execute, grant_source
)
values
    (
        '30000000-0000-4000-8000-000000000001',
        '3aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        '00000000-0000-4000-8000-000000000201',
        '{"resource_type":"device","resource_ids":["a"],"operations":["read"]}',
        repeat('a', 64), 'ACTIVE', 'NEVER', false, 'USER_EXPLICIT'
    ),
    (
        '30000000-0000-4000-8000-000000000002',
        '3bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        '00000000-0000-4000-8000-000000000201',
        '{"resource_type":"device","resource_ids":["b"],"operations":["read"]}',
        repeat('b', 64), 'ACTIVE', 'NEVER', false, 'USER_EXPLICIT'
    );

insert into public.authorization_decisions (
    id, user_id, permission_id, capability_key, action, scope, scope_digest,
    decision, reason_codes, risk_level, confirmation_required, scope_match,
    financial_guard_triggered
)
values (
    '30000000-0000-4000-8000-000000000003',
    '3bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    '30000000-0000-4000-8000-000000000002',
    'device.read', 'read',
    '{"resource_type":"device","resource_ids":["b"],"operations":["read"]}',
    repeat('b', 64), 'REQUIRE_CONFIRMATION', '["CONFIRMATION_REQUIRED"]', 1,
    true, true, false
);

insert into public.confirmation_requests (
    id, user_id, authorization_decision_id, permission_id, capability_key,
    action, scope_digest, status, expires_at
)
values (
    '30000000-0000-4000-8000-000000000004',
    '3bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    '30000000-0000-4000-8000-000000000003',
    '30000000-0000-4000-8000-000000000002',
    'device.read', 'read', repeat('b', 64), 'PENDING', now() + interval '5 minutes'
);

insert into public.audit_events (
    id, user_id, actor_type, event_type, capability_key, action, result,
    reason_codes, metadata
)
values (
    '30000000-0000-4000-8000-000000000005',
    '3bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    'USER', 'AUTHORIZATION_DENIED', 'device.read', 'read', 'DENIED',
    '["NO_PERMISSION"]', '{}'
);

set local role authenticated;
set local request.jwt.claims =
    '{"sub":"31111111-1111-1111-1111-111111111111","role":"authenticated"}';

select results_eq(
    $$select id from public.permissions order by id$$,
    array['30000000-0000-4000-8000-000000000001'::uuid],
    'User A can SELECT only its own permission'
);

select is_empty(
    $$select * from public.confirmation_requests
      where user_id = '3bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'::uuid$$,
    'User A cannot SELECT User B confirmation'
);

select is_empty(
    $$select * from public.audit_events
      where user_id = '3bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'::uuid$$,
    'User A cannot SELECT User B audit'
);

select throws_ok(
    $$insert into public.permissions (
        id, user_id, capability_id, scope, scope_digest, status,
        confirmation_policy, auto_execute, grant_source
      ) values (
        gen_random_uuid(), '3bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        '00000000-0000-4000-8000-000000000201', '{}', repeat('c', 64),
        'ACTIVE', 'NEVER', false, 'USER_EXPLICIT'
      )$$,
    '42501', null, 'User A cannot INSERT another user''s permission'
);

select throws_ok(
    $$update public.permissions set status = 'REVOKED'
      where id = '30000000-0000-4000-8000-000000000002'::uuid$$,
    '42501', null, 'User A cannot UPDATE another user''s permission'
);

select throws_ok(
    $$update public.confirmation_requests set status = 'APPROVED'
      where id = '30000000-0000-4000-8000-000000000004'::uuid$$,
    '42501', null, 'User A cannot APPROVE another user''s confirmation'
);

select throws_ok(
    $$delete from public.audit_events
      where id = '30000000-0000-4000-8000-000000000005'::uuid$$,
    '42501', null, 'User A cannot DELETE another user''s audit'
);

select results_eq(
    $$select count(*)::bigint from public.permissions$$,
    array[1::bigint],
    'Denied writes preserve visible owner state'
);

select * from finish();
rollback;
