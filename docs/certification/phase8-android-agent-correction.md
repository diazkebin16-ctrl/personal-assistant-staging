# Phase 8 Android delivery and artifact correction

Version: 0.8.1

This correction removes the competing UI delivery path reported against 0.8.0. WorkManager and
`MessageDeliveryWorker` are now the only durable network-delivery route. Manual retry re-enqueues
the existing operation with the same operation ID and WorkManager unique name; it never creates a
new record or changes its idempotency key. The unused `deliverPending` entry point was removed.

The missing `.env.example` resulted from an artifact exclusion pattern that treated every
`.env.*` filename as secret. The tracked template is restored with empty sensitive values. The new
deterministic packager explicitly preserves `.env.example`, rejects populated sensitive template
values, and excludes real environment files, credentials, caches, databases, APKs, and build
outputs.

No backend authority, migration, RLS policy, Executor, Voice, Wake Word, external service, or
production environment is changed.
