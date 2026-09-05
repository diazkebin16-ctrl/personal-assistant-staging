# Nano/Luna benchmark observability

This benchmark is an internal, PUBLIC-fixture-only evaluation path. It does not change productive routing. GPT-5 Nano remains evaluation-only and GPT-5.6 Luna remains the productive FAST model.

## Durable result contract

Every real benchmark execution must supply both `--run-id` and `--result-dir`. On Railway, `--result-dir` must point at the dedicated benchmark volume namespace. The runner persists one strict JSON document per run at:

`<result-dir>/<run-id>/result.json`

The document contains only benchmark identity, case IDs, requested/reported model IDs, normalized status, incomplete reason, success flag, usage, latency, estimated cost, visible synthetic-fixture output needed for scoring, sanitized failure category, timestamps, benchmark/schema version, and derived aggregates. It never persists prompts, headers, environment variables, credentials, authorization tokens, user memory, or real conversations.

## Checkpoint and recovery semantics

Before each provider call, the runner atomically writes an `in_progress` checkpoint. After the provider returns, that record is atomically replaced with the finished normalized result. Writes use a same-directory temporary file, file `fsync`, `os.replace`, and directory `fsync`.

Finished records are immutable. `--resume` skips every finished case/model pair and therefore never repeats it. If a run contains an `in_progress` record, resume fails closed because the provider may already have consumed that call. An operator must not guess whether such a call happened. A fresh run ID is required unless the ambiguous record is resolved from external evidence.

`--max-calls` is an absolute ceiling for the run, including earlier checkpoints already present when resuming. There are no automatic retries.

A missing or corrupt canonical `result.json` fails closed. Stray temporary files are ignored and cannot replace a valid canonical checkpoint.

## Railway retrieval

Railway should mount a dedicated volume at `/benchmark-results`. Future benchmark commands should use a namespace such as:

`--result-dir /benchmark-results/nano-luna`

Results are then recoverable after the pre-deploy process exits by reading:

`/benchmark-results/nano-luna/<run-id>/result.json`

No public endpoint, health endpoint, or log-based export is used.

## Historical calls excluded from quantitative comparison

Two real GPT-5 Nano calls were consumed before durable benchmark observability existed:

1. `greeting`, `max_output_tokens=128`: the older implementation reported `MALFORMED_RESPONSE`; valid diagnostic metadata was not retained.
2. `greeting`, `max_output_tokens=256`: the call completed, but Railway pre-deploy stdout was not recoverable through the available tooling, so comparable telemetry was lost.

These two calls are historical consumption only. They are not valid rows in the future Nano-vs-Luna quantitative comparison and must not be reconstructed or imputed.

The valid comparison set begins only with runs whose complete structured telemetry is durably recoverable under this contract.
