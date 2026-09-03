# Memory API

All routes require a verified Supabase bearer identity and explicit Phase 2 permission.

## Create

`POST /api/v1/memories` accepts class, content, optional summary/subject/source device/reference,
importance, sensitivity, expiration, bounded metadata, and optional confirmation. Owner,
confidence, status, internal provenance, fingerprint, revision, and embeddings are server-owned.
Exact active duplicates return the canonical record.

## Retrieve

- `GET /api/v1/memories` supports `status` (`ACTIVE`, `ARCHIVED`, `EXPIRED`), `memory_class`,
  `source_type`, `subject`, `min_importance`, created-time bounds, `limit <= 100`, and offset.
- `GET /api/v1/memories/{id}` returns only an active owned record.
- `GET /api/v1/memories/{id}/revisions` returns owned, non-deleted revision history.

Normal lists exclude discardable memory unless its class is explicitly requested. Deleted records
are never returned.

## Mutate

- `PATCH /api/v1/memories/{id}` requires `expected_version` and changes only mutable semantic fields.
- `POST /api/v1/memories/{id}/archive` requires `expected_version` and is idempotent.
- `DELETE /api/v1/memories/{id}?expected_version=N` performs irreversible privacy deletion and is
  idempotent after success unless a per-action confirmation is replayed.

When policy requires confirmation, the response is `409 MEMORY_CONFIRMATION_REQUIRED` with a
specific `confirmation_id`. Approve it through the existing AAL2 Confirmation API and retry with
that ID. Denial is `403`; hidden/unavailable owner resources are `404`; stale versions are `409`;
invalid bounded input is `422`.

There is no public set-owner, set-state, provenance, restore, embedding, arbitrary query, event
mutation, or internal proposal endpoint.
