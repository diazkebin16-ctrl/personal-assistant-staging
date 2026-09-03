# ADR-0014: Server-authoritative Web Research boundary

Status: accepted for Phase 13.

## Decision

Implement Web Research as an internal Orchestrator delegate reached only through the canonical
Text Assistant message route. Reuse PermissionsEngine and AI Router. Keep search, pinned retrieval,
extraction, evidence, and citation validation as narrow provider-neutral modules. Ship no live
provider and default the feature off.

## Rejected alternatives

- Browser or Android search/fetch: duplicates authority and exposes clients directly to untrusted
  content and provider credentials.
- A public prompt/search proxy: lets callers select routing or bypass conversation policy.
- Model tool calls for arbitrary URLs: combines untrusted instructions with network authority.
- Reusing Task/Executor for informational retrieval: manufactures a side-effect delivery path and
  incorrectly grants web content operational authority.
- Writing retrieved content to Memory: changes the durability/privacy contract and can preserve
  attacker-controlled instructions.
- Permissive URL fetching followed by response filtering: validation after connection cannot stop
  SSRF or DNS rebinding.
- Model-authored URL citations: cannot guarantee provenance or prevent phantom references.

## Consequences

Production remains unavailable until an approved provider is configured and staging exercises
live DNS/TLS/provider behavior. The service returns explicit permission, confirmation, policy,
availability, and insufficient-evidence outcomes instead of silently falling back to uncited model
knowledge.

