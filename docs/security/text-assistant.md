# Text Assistant security boundary

Conversation is data, never authority. User and provider text cannot change Identity, permissions,
risk, confirmations, Safe Mode, model selection, capability/action vocabulary, Task state, Memory
policy, or the financial guard.

Conversation text is persisted only for owner-scoped continuity. Raw messages, prompts, Memory,
and provider responses are excluded from operational logs, traces, Audit metadata, and AI usage
records. Governance events continue to be recorded by Memory, AI Router, Orchestrator, Permission,
Risk, Confirmation, Task, and Financial Guard boundaries rather than duplicating transcripts.

RLS grants authenticated users owner-only SELECT and denies direct authenticated mutation. Backend
service operations apply validation, optimistic concurrency, sequence reservation, and idempotency.
The pgTAP suite requires a disposable Supabase staging environment for runtime certification.

