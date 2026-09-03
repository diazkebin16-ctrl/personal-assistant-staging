# Web client deployment preparation

Phase 12 does not deploy. The following is the required staging/runtime contract for a later,
separately authorized deployment.

## Build

Use Node.js 24 and npm 11:

```bash
cd apps/web
npm ci
npm run format
npm run lint
npm run typecheck
npm test
npm run build
```

Run `npm start` from `apps/web` after the build. The artifact intentionally excludes `dist`; each
environment builds from the locked source.

## Server-only production configuration

| Variable | Requirement |
|---|---|
| `WEB_PUBLIC_ORIGIN` | Exact external HTTPS origin, no path/query/credentials |
| `WEB_BACKEND_ORIGIN` | Fixed certified FastAPI HTTPS origin |
| `WEB_SUPABASE_URL` | Exact Supabase HTTPS origin |
| `WEB_SUPABASE_ANON_KEY` | Public anon/publishable key only |
| `WEB_ENABLE_HSTS` | `true` only after TLS termination is verified |
| `HOST` / `PORT` | Internal listener binding |

These values stay on the server. `/config.json` reveals only `/api/v1`, the public Supabase values
and build version, with `no-store`. The browser cannot choose the backend.

## Staging acceptance (`REQUIRES STAGING`)

Verify real Supabase login, refresh, logout and account switch; valid TLS and HSTS; CSP reports in
target browsers; reverse-proxy origin/header behavior; backend rate limits; multi-tab logout; 401
expiry; conversations, Memory and Confirmation against a seeded non-production account; and
mobile/tablet/desktop keyboard and screen-reader smoke tests. Use no production credentials in CI.

Rollback is a deployment concern: retain the previous immutable web image and server configuration.
No database migration is introduced by Phase 12.
