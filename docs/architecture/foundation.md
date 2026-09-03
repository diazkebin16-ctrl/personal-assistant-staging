# Phase 0 foundation architecture

## Decisions implemented

The repository is a monorepo centered on a modular Python/FastAPI monolith. Device-specific apps,
shared contracts, infrastructure documentation, tests, and operational documentation have clear
boundaries. Future modules exist only as package boundaries and contain no premature logic.

Configuration is owned by one Pydantic `Settings` class. It accepts only `local`, `staging`, or
`production` environments. External service settings are optional in Phase 0, allowing a secure
local startup without false dependencies or embedded credentials.

## Backend and health

The ASGI app is built through an application factory. `/health/live` confirms that the process can
respond. `/health/ready` reports only the application component because no database, queue, AI
provider, or external capability is connected. Its component map can be extended when real checks
exist; unverified services are never reported as healthy.

## Logging and observability

Logs are JSON with timestamp, level, logger, message, and environment. The formatter can add
`trace_id`, `task_id`, `execution_id`, `user_id`, and `device_id` when later supplied. Known secret
field names and bearer values are redacted. No OpenTelemetry or Sentry SDK is installed or
initialized; their integration points are central configuration and structured context.

## Environments and deployment

Local, staging, and production are explicit values. The backend reads `PORT`, and the `Procfile`
provides a Railway-ready command. No cloud resource or external service was created or modified.

## CI and maintenance

Pull-request CI installs the locked project, checks formatting and lint, runs strict mypy, and
executes pytest on Python 3.12. Dependabot opens weekly Python and GitHub Actions update pull
requests without auto-merge.

## Deferred by design

Identity/auth, complete permissions, audit behavior, memory, orchestration, AI/OpenAI, voice,
tasks, automations, proactive behavior, integrations, functional clients, persistence schemas,
RLS, telemetry exporters, Sentry initialization, and financial logic remain for approved later
phases. Modules should be imported and run only when needed.
