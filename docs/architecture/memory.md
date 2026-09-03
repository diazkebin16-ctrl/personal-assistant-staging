# Memory Core Architecture

## Domain boundary

Memory is a module of the existing modular monolith. It persists deliberately classified records;
it does not ingest every conversation message. A future model may emit a `MemoryProposal`, but only
the server-owned Memory Service may validate identity, provenance, capability/action authority,
risk, confirmation, ownership, bounds, deduplication, expiration, and persistence.

The canonical classes are:

- `TEMPORARY_CONTEXT`: expiring working context;
- `OPERATIONAL`: active project/workflow state;
- `PERSISTENT_PREFERENCE`: stable explicit preferences;
- `HISTORICAL_DECISION`: immutable chronological decisions;
- `DISCARDABLE`: low-value classified information excluded from ordinary retrieval/context packs.

## Persistence and chronology

`MemoryRecord` stores current state. `MemoryRevision` stores the pre-update semantic state in the
same transaction. `MemoryEvent` stores content-free lifecycle chronology. Security-relevant
create/update/archive/delete operations also append Phase 2 `AuditEvent` evidence without raw
memory content.

Updates are explicit and conditionally match `version`; stale operations fail. Historical decision
content is immutable. Preference updates preserve old content in revisions, allowing prior state
to be reconstructed.

## Deterministic identity and growth

Unicode NFKC, whitespace normalization, case-folding, class, and subject produce a SHA-256 exact
canonical fingerprint. A partial database unique index protects one active deterministic memory
per user/class/fingerprint. Repeated active preferences create a `DEDUPLICATED` event rather than
another row. Historical decisions deliberately have no deduplication key because repeated decisions
are distinct chronological events. No semantic-similarity or embedding deduplication exists.

## Archive, expiry, and privacy deletion

Archive hides a record from normal active retrieval while preserving content and history. Expiry is
evaluated lazily and atomically, so correctness does not depend on a cron worker. Deleted records are
never returned and have no restore route. Deletion replaces current and revision content, summary,
subject, source reference, metadata, fingerprint, and deduplication identity with a minimal
non-content tombstone. Owner/class/source/sensitivity/timestamps and content-free events remain for
governance. This preserves evidence without retaining the deleted private text.

## Retrieval and context efficiency

Public retrieval is owner-scoped and bounded to 100 rows with status, class, source, subject,
importance, and time filters. Normal lists exclude archived, expired, deleted, and discardable
records. Archived/expired retrieval must be explicit. The internal `MemoryContextPack` selects at
most five deterministic high-importance/recent items per category and prefers summaries, for a
hard maximum of 20 items. It is a service boundary, not a public raw-query API.

PostgreSQL text search is deferred because current bounded filters meet Phase 4 requirements.
No external search service is introduced.

## Vector and future AI integration

The physical pgvector column is deliberately deferred. Vector dimension, distance semantics, and
model-version compatibility cannot be selected safely before Phase 5 chooses an embedding provider
and model. Phase 4 stores summaries and stable record IDs and exposes an authorized retrieval
service suitable for later on-demand embeddings. It adds no fake vector, embedding model, OpenAI
call, AI Router, or Orchestrator.

## Domain relationships

Memory may retain a Task UUID as provenance after validating Task ownership. Task Engine does not
depend on Memory. Device provenance requires an active owned Device. This one-way identifier
linkage avoids circular service coupling.
