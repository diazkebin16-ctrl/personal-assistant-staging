# Task Engine Security

- Uncertain or hard-denied authority never queues work.
- Capability/action and financial safeguards remain Phase 2 authorities.
- Ownership comes only from `IdentityContext`; devices and parents are validated server-side.
- Idempotency has a database constraint and semantic fingerprint.
- Conditional status/version updates reject stale overwrite and double claim.
- Terminal states cannot revive; RUNNING cannot be user-cancelled in Phase 3.
- Metadata is bounded and uses the shared secret redactor.
- Task mutation and TaskEvent are atomic; security-relevant events share required audit evidence.
- RLS grants authenticated clients read-only access to owned Tasks, attempts, and events.

RLS and simultaneous PostgreSQL behavior are implemented and statically validated but require
authorized staging for runtime certification.
