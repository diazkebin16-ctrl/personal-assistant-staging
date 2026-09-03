# Web Research architecture

Phase 13 adds one server-authoritative information path:

`Text Assistant → Orchestrator → Research policy/PermissionsEngine → search/retrieval →
untrusted evidence boundary → AI Router synthesis → citation validation → Text Assistant`.

There is no public provider proxy, client-selected provider, client-selected research mode, tool
execution, Task creation, Memory ingestion, or parallel delivery path. `AssistantRequest` remains
the only public entry point. The server recognizes explicit research language and selects one of
`NO_RESEARCH`, `SEARCH`, `FETCH`, or `MULTI_SOURCE_RESEARCH`.

## Trust boundaries

- Identity comes only from the existing verified `IdentityContext`.
- `web.research` and its `search`, `fetch`, and `multi_source` actions are authorized by the
  existing `PermissionsEngine`. Risk, confirmation, Safe Mode, and audit semantics are reused.
- Sensitive and critical input is rejected before search, DNS, HTTP, or AI-provider work. Ordinary
  queries are minimized and identifier-shaped data is redacted. Memory is never added.
- A search provider returns only provider-neutral URL/title/snippet records. The registry rejects
  duplicates and rejects test-only providers in production. The default runtime has no live search
  adapter and `RESEARCH_ENABLED=false`, so it fails closed.
- Retrieval canonicalizes HTTP(S) URLs, rejects credentials/unsafe ports/internal hostnames,
  resolves and validates every address, pins the selected global IP, preserves TLS SNI, validates
  every redirect, and detects a changed DNS set for the same hostname.
- Retrieval accepts bounded identity-encoded `text/html` or `text/plain` only. It rejects
  compressed responses, unsupported media, oversized bodies, excessive redirects, and timeouts.
- HTML extraction ignores scripts, styles, templates, comments, and hidden/aria-hidden content.
- Extracted passages are explicitly serialized as `untrusted_evidence`. The trusted synthesis
  instruction says never to obey evidence instructions and requires structured claims containing
  only supplied evidence identifiers. Tool calling is disabled.
- The model cannot provide citation URLs. The server resolves evidence identifiers, checks lexical
  support, rejects phantom/deleted evidence, and creates immutable citation metadata.

## Bounds and caching

Default hard bounds are two search attempts, five fetches/sources, three redirects, 1 MB per
response, 3 MB total, 200,000 extracted characters per source, eight evidence items, one synthesis
call, eight seconds per retrieval, and twenty seconds for the overall operation. There are no
background retries. The small in-process TTL cache uses SHA-256 keys, a 128-entry limit, and a
five-minute lifetime; it stores only already-validated public documents and is not durable.

## Client compatibility

Backend message responses add a bounded `citations` array. The Web client renders content as text
and citations as separately validated HTTP(S) links with `noopener noreferrer`. Android/KMP
strictly decodes citation metadata and treats the field as empty for historical messages; it adds
no browser, second research implementation, or offline answer generator.

