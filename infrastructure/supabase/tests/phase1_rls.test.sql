-- Phase 1 pgTAP validation for a Supabase staging database.
-- Run only after applying Alembic head in a disposable Supabase test environment.
-- This file is not executed by local SQLite tests because SQLite has no PostgreSQL RLS.

begin;

select plan(7);

insert into auth.users (id, email)
values
    ('11111111-1111-1111-1111-111111111111', 'phase1-owner@example.invalid'),
    ('22222222-2222-2222-2222-222222222222', 'phase1-other@example.invalid');

insert into public.users (id, auth_user_id, display_name, status)
values
    (
        'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        '11111111-1111-1111-1111-111111111111',
        'Owner',
        'ACTIVE'
    ),
    (
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        '22222222-2222-2222-2222-222222222222',
        'Other',
        'ACTIVE'
    );

insert into public.devices (
    id,
    user_id,
    device_name,
    device_type,
    platform,
    device_identifier,
    capabilities
)
values
    (
        'aaaaaaaa-1111-1111-1111-111111111111',
        'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        'Owner Web',
        'WEB',
        'WEB',
        'owner-installation',
        '{}'
    ),
    (
        'bbbbbbbb-2222-2222-2222-222222222222',
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        'Other Web',
        'WEB',
        'WEB',
        'other-installation',
        '{}'
    );

set local role authenticated;
set local request.jwt.claims =
    '{"sub":"11111111-1111-1111-1111-111111111111","role":"authenticated"}';

select results_eq(
    $$select auth_user_id from public.users order by auth_user_id$$,
    array['11111111-1111-1111-1111-111111111111'::uuid],
    'User A can SELECT only its own profile'
);

select results_eq(
    $$select id from public.devices order by id$$,
    array['aaaaaaaa-1111-1111-1111-111111111111'::uuid],
    'User A can SELECT only its own devices'
);

select is_empty(
    $$select * from public.auth_sessions
      where user_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'::uuid$$,
    'User A cannot SELECT User B sessions'
);

select throws_ok(
    $$insert into public.devices (
        id, user_id, device_name, device_type, platform, device_identifier, capabilities
      ) values (
        gen_random_uuid(),
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        'Spoofed',
        'WEB',
        'WEB',
        'spoofed-installation',
        '{}'
      )$$,
    '42501',
    null,
    'User A cannot INSERT a device owned by User B'
);

select throws_ok(
    $$update public.devices
      set device_name = 'Changed'
      where id = 'bbbbbbbb-2222-2222-2222-222222222222'::uuid$$,
    '42501',
    null,
    'User A cannot UPDATE User B device'
);

select throws_ok(
    $$delete from public.devices
      where id = 'bbbbbbbb-2222-2222-2222-222222222222'::uuid$$,
    '42501',
    null,
    'User A cannot DELETE User B device'
);

select results_eq(
    $$select count(*)::bigint from public.devices$$,
    array[1::bigint],
    'Denied writes do not change visible ownership state'
);

select * from finish();
rollback;
