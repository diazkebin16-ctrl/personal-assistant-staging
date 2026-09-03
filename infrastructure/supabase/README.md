# Supabase Phase 6 foundation

No Supabase project or production resource was created. Phase 2 extends the portable SQLAlchemy
models and Alembic chain with permission, decision, confirmation, and audit tables plus PostgreSQL
RLS definitions. Phase 3 adds owner-readable, backend-mutable Task, TaskAttempt, and TaskEvent
tables. Phase 4 adds owner-readable, backend-mutable MemoryRecord, MemoryRevision, and MemoryEvent
tables. Phase 5 adds owner-readable, backend-mutable AI routing decisions and usage records. Phase
6 adds owner-readable, backend-mutable workflows, immutable plans, steps, and future envelopes.
Supabase Auth remains the authentication authority from Phase 1.

To validate in an authorized disposable staging project:

1. configure the server-side PostgreSQL URL and Supabase JWT/JWKS settings;
2. run `uv run alembic upgrade head`;
3. run `supabase test db` so all RLS suites execute;
4. confirm owner isolation for identity, permissions, confirmations, decisions, audit, tasks,
   attempts, task events, memory records, revisions, memory events, routing decisions, and usage
   records, orchestration workflows, plans, steps, and envelopes, plus denial of direct task-state,
   memory, model-selection, usage, workflow-state, plan, and envelope mutation.

Local SQLite tests validate schema constraints and migration round-trips, not PostgreSQL RLS runtime
behavior. Credentials must be supplied per environment and never stored in the repository.
