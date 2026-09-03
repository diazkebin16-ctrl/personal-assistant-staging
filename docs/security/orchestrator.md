# Orchestrator security boundary

The Orchestrator coordinates authority but owns none. Model output cannot grant permission, choose
risk, satisfy confirmation, lower sensitivity, change safe mode, select a model/provider, persist
Memory, or execute a Task/tool. Strict schemas reject unknown authority fields and executable code
is never interpreted as an action mechanism.

Capability/action pairs are checked against the server-owned Phase 2 vocabulary before Task
creation and again by the certified authorization pipeline. Revoked/expired permissions, disabled
capabilities, device mismatches, confirmation mismatch/replay/expiry, and evaluation failures fail
closed. Financial execution remains a hard deny even with a permission and confirmation.

Plan content becomes immutable before authorization. Scope and material arguments are hashed into
the plan fingerprint; there is no public mutation path. A later readiness reevaluation uses the
stored plan and the linked Task. It reparses and recomputes the plan hash before confirmation or
authorization reuse; any change fails closed before confirmation consumption. A changed plan
requires a new workflow and authority decision.

Prompt injection is content, not instruction authority. Retrieved Memory and user text are placed
inside an explicit untrusted-data envelope, while all consequential output must pass schemas,
Capability semantics, TaskService, and the full authority chain.

Audit and observability record IDs, state, intent category, reason codes, and safe metadata only.
They exclude input, prompt, response, Memory text, credentials, and tokens. RLS grants authenticated
users owner-scoped SELECT only; all direct mutations remain backend-owned.
