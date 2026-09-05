# Server-owned model catalog

The catalog is code/config-defined rather than client- or database-authored in Phase 5. This keeps
model identifiers, capabilities, privacy approval, enablement, routing eligibility, evaluation
eligibility, deprecation, context limits, output limits, quality, latency, pricing metadata, and
fallback priority under server control.

Canonical classes are `FAST`, `STANDARD`, `ADVANCED`, `REALTIME`, `EMBEDDING`, and `LOCAL`.
Capabilities are declared independently (`TEXT_GENERATION`, `STRUCTURED_OUTPUT`, `TOOL_CALLING`,
`STREAMING`, `AUDIO_REALTIME`, and `EMBEDDINGS`). A model is eligible only when it declares every
required capability.

Provider and model identifiers are unique. Models cannot reference unknown providers. Disabled
providers/models and deprecated models are never selected. `enabled` means operational availability;
`routing_enabled` independently controls normal routing eligibility; and `evaluation_enabled`
allows an explicitly invoked internal candidate evaluation.

## Current staging provider and models

OpenAI is the only external provider. GPT-5.6 Luna, Terra, and Sol retain their existing normal
routing and privacy configuration. GPT-5 Nano (`gpt-5-nano`) is an evaluation-only candidate under
the same provider: `evaluation_enabled=True`, `routing_enabled=False`.

The Nano definition uses OpenAI API documentation verified on 2026-09-05: 400,000-token context,
128,000-token maximum output, USD 0.05 per million input tokens, USD 0.005 per million cached input
tokens, and USD 0.40 per million output tokens. OpenAI documents Responses API compatibility,
streaming, function calling, and Structured Outputs. Lex currently exposes only capabilities safely
implemented by its provider abstraction; candidate evaluation does not add a public tool surface.

## Privacy and promotion

Nano inherits no new authorization merely because it shares the OpenAI provider. The existing
OpenAI provider boundary remains approved through `PRIVATE`, while `SENSITIVE` and `CRITICAL` remain
restricted. Existing consent, context gating, Memory gating, and trust boundaries are unchanged.

Promoting Nano later requires an explicit reviewed catalog/routing change. Price alone must never
make a candidate routable or place it into fallback.

The bundled default catalog remains intentionally non-operational: all placeholder providers/models
are disabled. Operational catalog updates must be reviewed server-side because provider pricing,
capabilities, privacy terms, and availability can change.
