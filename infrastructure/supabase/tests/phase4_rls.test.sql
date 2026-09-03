-- Phase 4 pgTAP validation for an authorized disposable Supabase staging database.
-- Apply Alembic head first. This file is not a claim of local runtime validation.

begin;

select plan(8);

insert into auth.users (id, email)
values
    ('51111111-1111-1111-1111-111111111111', 'phase4-owner@example.invalid'),
    ('52222222-2222-2222-2222-222222222222', 'phase4-other@example.invalid');

insert into public.users (id, auth_user_id, display_name, status)
values
    ('5aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '51111111-1111-1111-1111-111111111111', 'Owner', 'ACTIVE'),
    ('5bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', '52222222-2222-2222-2222-222222222222', 'Other', 'ACTIVE');

insert into public.memory_records (
    id, user_id, memory_class, status, source_type, content, normalized_content,
    confidence, importance, sensitivity, fingerprint, deduplication_key, version, metadata
)
values
    (
        '50000000-0000-4000-8000-000000000011',
        '5aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'OPERATIONAL', 'ACTIVE',
        'USER_EXPLICIT', 'Owner memory', 'Owner memory', 100, 70, 'PRIVATE',
        repeat('1', 64), repeat('1', 64), 1, '{}'
    ),
    (
        '50000000-0000-4000-8000-000000000012',
        '5bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'PERSISTENT_PREFERENCE', 'ACTIVE',
        'USER_EXPLICIT', 'Other memory', 'Other memory', 100, 70, 'SENSITIVE',
        repeat('2', 64), repeat('2', 64), 1, '{}'
    );

insert into public.memory_revisions (
    id, memory_id, revision_number, memory_class, source_type, content,
    normalized_content, confidence, importance, sensitivity, fingerprint, actor_type, metadata
)
values (
    '50000000-0000-4000-8000-000000000021',
    '50000000-0000-4000-8000-000000000012', 1, 'PERSISTENT_PREFERENCE',
    'USER_EXPLICIT', 'Previous other memory', 'Previous other memory', 100, 70,
    'SENSITIVE', repeat('3', 64), 'USER', '{}'
);

insert into public.memory_events (
    id, memory_id, user_id, event_type, to_status, actor_type, reason_code, metadata
)
values (
    '50000000-0000-4000-8000-000000000031',
    '50000000-0000-4000-8000-000000000012',
    '5bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'CREATED', 'ACTIVE',
    'USER', 'MEMORY_STORED', '{}'
);

set local role authenticated;
set local request.jwt.claims =
    '{"sub":"51111111-1111-1111-1111-111111111111","role":"authenticated"}';

select results_eq(
    $$select id from public.memory_records order by id$$,
    array['50000000-0000-4000-8000-000000000011'::uuid],
    'User A can SELECT only its own memory rows'
);

select is_empty(
    $$select * from public.memory_revisions
      where memory_id = '50000000-0000-4000-8000-000000000012'::uuid$$,
    'User A cannot SELECT User B memory revisions'
);

select is_empty(
    $$select * from public.memory_events
      where user_id = '5bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'::uuid$$,
    'User A cannot SELECT User B memory events'
);

select throws_ok(
    $$update public.memory_records set user_id = '5bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
      where id = '50000000-0000-4000-8000-000000000011'::uuid$$,
    '42501', null, 'Authenticated client cannot alter protected memory ownership'
);

select throws_ok(
    $$insert into public.memory_records (
        id, user_id, memory_class, status, source_type, content, normalized_content,
        confidence, importance, sensitivity, fingerprint, version, metadata
      ) values (
        gen_random_uuid(), '5aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'OPERATIONAL',
        'ACTIVE', 'SYSTEM', 'Spoofed', 'Spoofed', 100, 100, 'PUBLIC', repeat('4', 64), 1, '{}'
      )$$,
    '42501', null, 'Authenticated client cannot forge memory provenance or state'
);

select throws_ok(
    $$delete from public.memory_records
      where id = '50000000-0000-4000-8000-000000000011'::uuid$$,
    '42501', null, 'Authenticated client cannot bypass deterministic privacy deletion'
);

select throws_ok(
    $$update public.memory_revisions set content = 'tampered'
      where id = '50000000-0000-4000-8000-000000000021'::uuid$$,
    '42501', null, 'Authenticated client cannot tamper with MemoryRevision history'
);

select throws_ok(
    $$delete from public.memory_events
      where id = '50000000-0000-4000-8000-000000000031'::uuid$$,
    '42501', null, 'Authenticated client cannot tamper with MemoryEvent history'
);

select * from finish();
rollback;
