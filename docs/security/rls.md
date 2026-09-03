# Row Level Security

## Policy

RLS is enabled on Phase 1 identity tables and Phase 2 `permissions`,
`authorization_decisions`, `confirmation_requests`, and `audit_events` in PostgreSQL. Phase 3
adds Task tables, Phase 4 adds Memory tables, Phase 5 adds AI routing/usage tables, and Phase 6
adds workflows, immutable plans, steps, and future-action envelopes. Phase 7 adds Conversation
history, and Phase 9 adds backend-only VoiceSession/VoiceTurn delivery evidence. The `anon` and
`authenticated` roles first lose all table privileges. The
authenticated role receives SELECT only, with one owner-scoped policy per user table:

- users match `auth.uid()` to `auth_user_id`;
- devices resolve their internal owner and match that user's `auth_user_id`;
- sessions resolve their internal owner in the same way.
- Phase 2–7 rows resolve their internal owner and match that user's `auth_user_id`.
- deleted MemoryRecord content and its revisions are not selectable by authenticated clients.

Phase 9 voice tables are stricter: RLS is enabled and forced, all `anon`/`authenticated`
privileges are revoked, and no client policy exists. Credentials, provider/model selection, and
turn delivery evidence are available only through the owner/device/session-validated backend API.

Authenticated users may read only enabled rows from the global `capabilities` catalog.

No direct INSERT, UPDATE, or DELETE grants/policies exist. Writes occur through the
backend, which separately derives ownership from the verified `IdentityContext`. RLS and backend
ownership checks are complementary.

## Validation status

- SQLite migration upgrade/downgrade/re-upgrade: **TESTED**.
- RLS statements and least-privilege grants: **INSPECTED** by automated tests.
- Cross-user API ownership: **TESTED** against the real service/database layer with SQLite.
- PostgreSQL/Supabase RLS runtime: **REQUIRES STAGING**.

`infrastructure/supabase/tests/phase1_rls.test.sql` through `phase7_rls.test.sql`, plus
`phase9_rls.test.sql`, are transactional
pgTAP suites for a disposable Supabase staging environment. Phase 6 covers workflow/plan/step/
envelope isolation plus denial of direct state, plan, and envelope mutations. Phase 9 verifies
forced RLS and zero direct client privileges on voice authority metadata. Local
results must never be presented as PostgreSQL RLS runtime evidence.
