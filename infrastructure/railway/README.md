# Railway foundation

No Railway project or service is created or modified through Phase 1. A future service can install from
`pyproject.toml` and use the root `Procfile`. The entry point reads the platform-provided `PORT`,
binds on all interfaces, and exposes `/health/live` and `/health/ready`.

Environment values must be configured in Railway rather than committed. Staging and production
must be separate environments. Deployment requires explicit authorization.
