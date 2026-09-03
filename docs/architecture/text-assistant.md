# Phase 7 Text Assistant architecture

The Text Assistant is the authenticated conversational interface, not an authority layer. Normal
text uses a bounded recent-history pack and optional owner-scoped `MemoryContextPack`, calculates
the highest effective sensitivity, then invokes a provider only through `AIRouter`. Action-shaped
requests are delegated to `OrchestratorService`; explicit memory commands use `MemoryService`.

Conversation history, long-term Memory, AI usage telemetry, and Audit remain separate domains. A
message never becomes Memory automatically, and model output cannot grant permission, lower risk,
satisfy confirmation, alter Safe Mode, or create executable authority.

## Context and truth boundary

- At most 12 complete recent messages and 20,000 history characters enter model context.
- Older messages remain durable and owner-visible; Phase 7 does not perform AI summarization.
- System instructions are centralized and versioned in `text_assistant/instructions.py`.
- Memory is fetched only through `MemoryService`, retaining provenance and sensitivity.
- The effective sensitivity is the maximum of system, current message, history, and Memory context.
- `CRITICAL` requires eligible local routing or is denied by Phase 5 policy.
- Responses distinguish generated text, stored/deleted Memory, confirmation waits, permission
  waits, future-execution readiness, denial, and failure.

## Durability and concurrency

`Conversation.version` and a conditional update reserve each user/assistant sequence pair.
`UNIQUE(user_id, idempotency_key)` prevents duplicate message submissions, while a server-derived
fingerprint rejects reuse for materially changed requests. PostgreSQL simultaneous-race behavior
requires staging certification; correctness does not depend on a process-local lock.

Action coordination passes only the current explicit request into Phase 6. Conversation history is
not implicitly reinterpreted as action arguments. Phase 7 has no Executor or external side effects.

