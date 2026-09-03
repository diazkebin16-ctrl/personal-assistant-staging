# Provider abstraction

`LLMProvider` is the minimal Phase 5 protocol: a stable provider key and an asynchronous generation
method accepting a provider-neutral request. Core policy contains no OpenAI-, Anthropic-, Gemini-,
or local-runtime-specific logic.

`ProviderRegistry` is server-constructed and rejects duplicate adapters. Missing adapters fail as
`PROVIDER_UNAVAILABLE`. `FakeProvider` provides deterministic no-network validation. No disabled
skeleton claims to contact a live provider.

Failure classes are centralized. Availability, rate limit, timeout, and internal-provider failures
are retryable; authentication, invalid request, context, content policy, unsupported capability,
malformed response, and cancellation failures are permanent. Attempts are bounded. Equivalent
fallbacks precede stronger quality escalation, and weaker degradation is not generated.

Raw input/output is ephemeral. It is absent from routing decisions, usage rows, audit metadata,
metrics, and default logs. Tool-call capability is selection metadata only; the protocol has no tool
executor.

