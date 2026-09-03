# Memory Security

## Authority and ownership

Every public operation derives the owner from verified `IdentityContext` and invokes the existing
Permissions Engine with a server-constructed scope. The capability catalog is authoritative:

- `memory.read`: `read`;
- `memory.write`: `create`, `update`, `archive`;
- `memory.delete`: `delete`.

Permission scopes can narrow these actions but cannot invent new ones. Delete is server-classified
high risk and destructive; confirmation follows the existing permission policy. There is no
memory-specific risk or confirmation bypass.

Public creation is always `USER_EXPLICIT` with server-set confidence 100. System, Task, Device, and
Import provenance use an internal proposal method and are validated. `FUTURE_AI_PROPOSAL` is a
classification value but cannot persist during Phase 4. Task references and source devices must
belong to the owner; revoked devices fail closed.

## Content and privacy

Content, summaries, subjects, source references, metadata entries, nesting, nodes, and serialized
size are bounded. Metadata uses the shared secret redactor. Raw memory content is intentionally
returned only to its authenticated owner and is never placed in logs, MemoryEvent, or AuditEvent.

Soft deletion is a privacy tombstone, not recoverable archive. It scrubs all current and revision
text plus metadata and destroys the deduplication key. Normal API/RLS paths cannot retrieve or
restore it. Minimal identifiers, classification, timestamps, and content-free events remain to
prove that deletion occurred and prevent silent resurrection.

## Concurrency and database defense

Updates, archives, expiry, and deletion use status/version conditional writes. Current-state
mutation and MemoryEvent/AuditEvent persistence share one transaction. A partial unique index is
the final duplicate-create race guard. SQLite validates constraints and stale writes locally;
simultaneous PostgreSQL races and live RLS remain staging requirements.

RLS grants authenticated users only owner-scoped SELECT. It grants no direct INSERT, UPDATE, or
DELETE on memory, revisions, or events. Backend checks and RLS are complementary.
