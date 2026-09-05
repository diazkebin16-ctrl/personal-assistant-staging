# Server-owned model catalog

The catalog is code/config-defined rather than client- or database-authored in Phase 5. This keeps
model identifiers, capabilities, privacy approval, enablement, routing eligibility, evaluation
eligibility, deprecation, context limits, output limits, quality, latency, pricing metadata, and
fallback priority under server control.

Canonical classes are `FAST`, `STANDARD`, `ADVANCED`, `REALTIME`, `EMBEDDING`, and `LOCAL`.
Capabilities are declared independently (`TEXT_GENERATION`, `STRUCTURED_OUTPUT`, `TOOL_CALLING`,
`STREAMING`, `AUDIO_REALTIME`, and `EMBEDDINGS`). A model is eligible only when it declares every
required capability.

Provider and model identifiers are unique. Models cannot reference unknown providers. REALTIME and
EMBEDDING definitions must declare their matching capability. Disabled providers/models and
deprecated models are never selected. `enabled` means the definition is operationally available;
`routing_enabled` independently controls normal routing eligibility; and `evaluation_enabled`
allows an explicitly invoked internal candidate evaluation. An enabled model that is neither
routable nor evaluation-enabled is invalid.

## Current staging providers

OpenAI remains the normal routed provider with GPT-5.6 Luna, Terra, and Sol. Their existing routing
and privacy configuration is unchanged.

Google Gemini is independently optional and currently contains one candidate model:
`gemini-2.5-flash-lite`. It declares only `TEXT_GENERATION`, because the first adapter does not
implement structured output or tool calling. It is `evaluation_enabled=True` and
`routing_enabled=False`, so its lower price cannot affect normal selection or fallback ordering.

Gemini's pricing metadata uses Google's published Gemini API standard paid rates verified on
2026-09-04: USD 0.10 per million input text/image/video tokens and USD 0.40 per million output
tokens (including thinking tokens). Pricing metadata is evidence for cost estimation only and is
not used to disguise candidate state.

## Privacy and promotion

Privacy authorization is provider-specific. OpenAI's existing `PRIVATE` approval is not inherited
by Gemini. The Gemini provider and candidate model are limited to `PUBLIC`; they have no PRIVATE,
SENSITIVE, or CRITICAL approval.

Promoting a candidate later requires an explicit reviewed catalog change to `routing_enabled=True`.
That promotion is separate from provider enablement and separate from any future privacy approval.
Neither promotion nor a credential alone grants additional data sensitivity access.

The bundled default catalog remains intentionally non-operational: all placeholder providers/models
are disabled. Operational catalog updates must be reviewed server-side because provider pricing,
capabilities, privacy terms, and availability can change.
