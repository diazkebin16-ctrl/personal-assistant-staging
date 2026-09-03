-- Phase 5 pgTAP validation for an authorized disposable Supabase staging database.
-- Apply Alembic head first. This file is not a claim of local runtime validation.

begin;

select plan(6);

insert into auth.users (id, email)
values
    ('61111111-1111-1111-1111-111111111111', 'phase5-owner@example.invalid'),
    ('62222222-2222-2222-2222-222222222222', 'phase5-other@example.invalid');

insert into public.users (id, auth_user_id, display_name, status)
values
    ('6aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '61111111-1111-1111-1111-111111111111', 'Owner', 'ACTIVE'),
    ('6bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', '62222222-2222-2222-2222-222222222222', 'Other', 'ACTIVE');

insert into public.ai_routing_decisions (
    id, user_id, outcome, provider_key, model_id, model_class, selected_quality,
    policy_version, reason_codes, required_capabilities, effective_sensitivity,
    estimated_input_tokens, requested_output_tokens, fallback_chain, estimated_cost_microunits
)
values
    (
        '60000000-0000-4000-8000-000000000011',
        '6aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'SELECTED', 'approved-provider',
        'standard-model', 'STANDARD', 2, 'ai-router-v1', '["DEFAULT_STANDARD"]',
        '["TEXT_GENERATION"]', 'PRIVATE', 100, 100, '[]', 10
    ),
    (
        '60000000-0000-4000-8000-000000000012',
        '6bbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'DENIED', null, null, null, null,
        'ai-router-v1', '["SENSITIVITY_RESTRICTION"]', '["TEXT_GENERATION"]',
        'CRITICAL', 100, 100, '[]', null
    );

insert into public.ai_usage_records (
    id, user_id, routing_decision_id, provider_key, model_id, attempt_number,
    input_tokens, output_tokens, cached_tokens, latency_ms, outcome,
    estimated_cost_microunits
)
values
    (
        '60000000-0000-4000-8000-000000000021',
        '6aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        '60000000-0000-4000-8000-000000000011', 'approved-provider',
        'standard-model', 1, 80, 20, 0, 30, 'SUCCESS', 8
    );

set local role authenticated;
set local request.jwt.claims =
    '{"sub":"61111111-1111-1111-1111-111111111111","role":"authenticated"}';

select results_eq(
    $$select id from public.ai_routing_decisions order by id$$,
    array['60000000-0000-4000-8000-000000000011'::uuid],
    'User A can SELECT only its own routing decisions'
);

select results_eq(
    $$select id from public.ai_usage_records order by id$$,
    array['60000000-0000-4000-8000-000000000021'::uuid],
    'User A can SELECT only its own usage records'
);

select throws_ok(
    $$insert into public.ai_routing_decisions (
        id, user_id, outcome, policy_version, reason_codes, required_capabilities,
        effective_sensitivity, estimated_input_tokens, requested_output_tokens, fallback_chain
      ) values (
        gen_random_uuid(), '6aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'DENIED',
        'forged', '["NO_ELIGIBLE_MODEL"]', '[]', 'PUBLIC', 0, 1, '[]'
      )$$,
    '42501', null, 'Authenticated client cannot forge routing decisions'
);

select throws_ok(
    $$update public.ai_routing_decisions set model_id = 'forced-model'
      where id = '60000000-0000-4000-8000-000000000011'::uuid$$,
    '42501', null, 'Authenticated client cannot override a selected model'
);

select throws_ok(
    $$insert into public.ai_usage_records (
        id, user_id, routing_decision_id, provider_key, model_id, attempt_number,
        input_tokens, output_tokens, cached_tokens, latency_ms, outcome,
        estimated_cost_microunits
      ) values (
        gen_random_uuid(), '6aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        '60000000-0000-4000-8000-000000000011', 'forged', 'forged', 2,
        0, 0, 0, 0, 'FAILURE', 0
      )$$,
    '42501', null, 'Authenticated client cannot forge usage telemetry'
);

select throws_ok(
    $$delete from public.ai_usage_records
      where id = '60000000-0000-4000-8000-000000000021'::uuid$$,
    '42501', null, 'Authenticated client cannot tamper with usage history'
);

select * from finish();
rollback;
