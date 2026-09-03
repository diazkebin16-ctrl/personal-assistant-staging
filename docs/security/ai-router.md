# AI Router security

## Selection authority

Model/provider definitions, provider health, sensitivity approvals, quality floors, and budgets are
server-owned. No public `force_model`, `force_provider`, `skip_router`, or `ignore_sensitivity`
surface exists. Routing request schemas reject extra fields.

## Sensitivity

- `PUBLIC` and `INTERNAL` require catalog-declared allowance.
- `PRIVATE` also requires explicit provider private-data approval.
- `SENSITIVE` requires explicit sensitive-data approval.
- `CRITICAL` requires an explicitly approved local provider and LOCAL routing; otherwise routing is
  denied.

The effective class is the highest of request and MemoryContextPack item classifications. Missing
proof fails closed. These flags describe configured policy only; they make no unverified claim about
a provider contract or retention behavior.

## Authority isolation

Model output is advisory data. It cannot grant permission, lower risk, approve confirmation, create
an executable Task, persist arbitrary Memory, call a tool, or override the financial guard.
`finance.execute` remains default-deny in Phase 2 regardless of model class or output.

## Privacy

Prompts, outputs, memory text, tokens, and credentials are excluded from decisions, usage records,
audit, observer events, and default logs. RLS exposes only owner rows for decisions/usage and denies
direct authenticated mutation. Live Supabase enforcement still requires staging certification.

