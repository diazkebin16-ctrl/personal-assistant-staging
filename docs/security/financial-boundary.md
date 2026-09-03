# Financial Safety Boundary

Phase 2 permits classification and scoped read authority but never financial execution.

`finance.read` is separate from `finance.execute`. The latter, and financial actions such as
`buy`, `sell`, `transfer`, `withdraw`, `deposit`, `change_leverage`, `increase_risk`,
`place_order`, and financially consequential `cancel_order`, are always denied by the
`FinancialExecutionGuard`.

The guard is evaluated after permission and risk checks but is superior to confirmation policy,
`auto_execute`, and client input. A valid permission cannot disable it. Caller-supplied risk is
not authoritative and cannot lower the server-computed critical level. Triggered attempts create
both denial evidence and a dedicated `FINANCIAL_GUARD_TRIGGERED` audit event.

No broker, bank, OANDA, BotsTrader, payment provider, or money movement integration exists in
this phase.
