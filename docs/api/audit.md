# Audit API

`GET /api/v1/audit?limit=50&offset=0`

The authenticated user receives only their events, newest first. `limit` is constrained to
1–100 and `offset` to 0–100000. The controlled response omits internal ORM state and contains only
redacted, bounded metadata.

There is no create, update, or delete audit API. Events are emitted by authority services.
