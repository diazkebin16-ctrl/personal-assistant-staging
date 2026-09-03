# Contributing

## Workflow

1. Create a focused branch from the current canonical branch.
2. Make small, reviewable changes. Do not develop directly on `main`.
3. Run formatting, lint, type checking, tests, and compile validation locally.
4. Open a pull request and require CI to pass before merge.

New dependencies require a concrete need and review. Do not change the approved architecture,
providers, or security decisions without architectural approval. Never commit secrets, weaken a
test to force a pass, hide errors, or bundle unrelated changes.
