# Server-owned model catalog

The catalog is code/config-defined rather than client- or database-authored in Phase 5. This keeps
model identifiers, capabilities, privacy approval, enablement, deprecation, context limits, output
limits, quality, latency, pricing metadata, and fallback priority under server control.

Canonical classes are `FAST`, `STANDARD`, `ADVANCED`, `REALTIME`, `EMBEDDING`, and `LOCAL`.
Capabilities are declared independently (`TEXT_GENERATION`, `STRUCTURED_OUTPUT`, `TOOL_CALLING`,
`STREAMING`, `AUDIO_REALTIME`, and `EMBEDDINGS`). A model is eligible only when it declares every
required capability.

Provider and model identifiers are unique. Models cannot reference unknown providers. REALTIME and
EMBEDDING definitions must declare their matching capability. Disabled providers/models and
deprecated models are never selected. `enabled` is a restrictive feature switch and cannot bypass
sensitivity or quality policy.

The bundled catalog is intentionally non-operational: all provider/model placeholders are disabled.
Its price entries are schema-validation metadata, not current third-party price claims. Operational
catalog updates must be reviewed server-side because provider pricing and privacy terms are mutable.

