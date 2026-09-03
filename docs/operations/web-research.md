# Web Research operations

`RESEARCH_ENABLED` defaults to `false`. Do not enable it merely by changing client configuration.
The backend must be supplied an approved server-side `SearchProvider` adapter through composition;
test adapters are rejected when `ENVIRONMENT=production`. No provider implementation or credential
is included in the Phase 13 artifact.

Before staging enablement:

1. approve the provider's privacy, retention, jurisdiction, terms, quotas, and failure semantics;
2. store credentials in the deployment secret manager, never source or public runtime config;
3. verify outbound DNS/TLS, IP pinning, redirects, IPv4/IPv6, rate limits, timeouts, and cancellation;
4. grant `web.research` scopes to designated test identities and exercise permission, confirmation,
   revocation, Safe Mode, and audit flows;
5. validate citation quality against known public corpora and adversarial prompt-injection pages;
6. confirm metadata-only logs/metrics and alert on blocked URL, rebinding, integrity, rate-limit,
   timeout, and provider-unavailable outcomes;
7. keep a kill path via `RESEARCH_ENABLED=false` and Safe Mode.

No production deployment, secret insertion, paid call, or live-provider test is part of source
certification.
