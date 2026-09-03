# ADR-0005: Memory Architecture

## Decision

Implement classified owner-scoped memory inside the modular monolith using `MemoryRecord` current
state, privacy-scrubbable `MemoryRevision` snapshots, and content-free append-oriented
`MemoryEvent` chronology. Use existing Identity, Permissions/Risk/Confirmation, Audit, Device, and
Task identifiers as authority boundaries rather than duplicating them.

Public memory is explicitly user-originated. Future model output remains a non-authoritative
proposal. Exact normalized duplicates use a server-owned SHA-256 identity and a partial database
unique index; historical decisions intentionally remain separate. Semantic updates use optimistic
versions, historical decisions are immutable, archive preserves content, expiry is lazy, and delete
irreversibly scrubs current/revision payloads while retaining a minimal governance tombstone.

Retrieval is bounded and deterministic. A maximum-20-item context pack uses summaries and selective
category loading. PostgreSQL full-text search is deferred until required. Physical pgvector and
embedding fields are deferred until Phase 5 selects a provider/model and therefore a defensible
dimension and versioning policy.

## Rationale

This architecture preserves provenance, user ownership, historical reconstruction, privacy
deletion, bounded growth, and future semantic retrieval without treating conversation noise as
permanent memory. Deduplication, summaries, and bounded context reduce cost without reducing stored
memory quality. PostgreSQL remains sufficient; no external search, vector, cache, or queue service
is introduced.

## Consequences

Deleted content cannot be restored through normal APIs. Historical revisions intentionally retain
prior text until privacy deletion, when they are scrubbed. Simultaneous PostgreSQL race behavior,
live Supabase RLS, and live JWT/JWKS remain staging validations. AI extraction, embeddings,
semantic ranking, AI Router, and Orchestrator remain outside Phase 4.
