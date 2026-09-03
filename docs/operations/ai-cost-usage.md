# AI cost and usage foundation

Pricing is isolated in versioned catalog metadata using integer currency microunits per million
tokens. Estimates are deterministic ceiling projections. They are never labeled as actual charges.
An actual cost remains nullable until a future provider supplies trustworthy billing metadata.

The quality-first ordering is fixed:

1. required quality and capabilities;
2. security and sensitivity;
3. reliability and health;
4. equivalent-candidate cost comparison.

Per-request, daily, and monthly soft thresholds produce warnings. Explicit hard limits deny safely;
they do not reroute complex work to an inadequate model. Aggregate spend arrives through a trusted
snapshot, not through `RoutingRequest`.

Usage rows contain provider/model identifiers, tokens, cached tokens, latency, outcome, classified
failure, estimated cost, optional actual cost, user, task, decision, and timestamp. They contain no
prompt, response, Memory content, token credential, or provider secret. Ordinary usage is telemetry,
not AuditEvent volume.

