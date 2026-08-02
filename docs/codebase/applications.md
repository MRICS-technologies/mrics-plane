# Applications

One source-backed subsection for each application under `apps/`. Each entry identifies the manifest/entry path and the responsibility that the manifests, Dockerfiles, and entry points actually support. Where a component's responsibility cannot be verified from these artifacts, that is stated explicitly.

## API — `apps/api/`

- **Manifest/entry**: [`manage.py`](../../apps/api/manage.py) (defaults `DJANGO_SETTINGS_MODULE` to `plane.settings.production`), [`Dockerfile.api`](../../apps/api/Dockerfile.api) (Python 3.12-alpine), [`pyproject.toml`](../../apps/api/pyproject.toml) (`name = "Plane"`, ruff config), [`requirements.txt`](../../apps/api/requirements.txt) (`-r requirements/production.txt`).
- **Responsibility**: the Django/DRF backend that powers Plane. It is built from `apps/api` via `Dockerfile.api`, excluded from the pnpm workspace ([`pnpm-workspace.yaml`](../../pnpm-workspace.yaml) lists `!apps/api`), and depended on at runtime by web, admin, and space (per the root graph's `depends_on` edges).
- **Runtime processes**: the production compose stack runs the same image with four entry scripts ([`docker-compose.yml`](../../docker-compose.yml)): `docker-entrypoint-api.sh` (gunicorn/Uvicorn ASGI server), `docker-entrypoint-worker.sh` (Celery worker), `docker-entrypoint-beat.sh` (Celery beat), and `docker-entrypoint-migrator.sh` (Django migrations).
- See [backend.md](./backend.md) for the full Django project structure.

## Web — `apps/web/`

- **Manifest/entry**: [`package.json`](../../apps/web/package.json) (`name: "web"`, `react-router dev --port 3000`), [`app/routes.ts`](../../apps/web/app/routes.ts) (merges `core` + `extended` route configs and appends a catch-all 404), [`react-router.config.ts`](../../apps/web/react-router.config.ts) (`ssr: false` — client-side SPA build), [`vite.config.ts`](../../apps/web/vite.config.ts).
- **Responsibility**: the main Plane user interface. Declares every principal `@plane/*` package as a workspace dependency (constants, editor, hooks, i18n, propel, services, shared-state, types, ui, utils — see [`package.json`](../../apps/web/package.json)) and depends on the API at runtime.
- **Serving**: `Dockerfile.web` builds a static client bundle and serves it with nginx on port 3000 (`apps/web/nginx/nginx.conf`). A PWA `manifest.json` is present under `apps/web/manifest.json`.
- **Scope note**: only the app shell and route tree are described here. Component-level detail is `Not yet documented` at graph level (planned per [graph-roadmap.md](./graph-roadmap.md#application-graphs)).

## Admin — `apps/admin/`

- **Manifest/entry**: [`package.json`](../../apps/admin/package.json) (`name: "admin"`, description "Admin UI for Plane", `react-router dev --port 3001`), [`app/routes.ts`](../../apps/admin/app/routes.ts).
- **Responsibility**: the instance-administration ("god-mode") UI. Its route table confirms the surface: instance `general` settings, `workspace` management, `email`, `authentication` (with GitHub/GitLab/Google/Gitea sub-pages), `ai`, `image`, and `github-app` configuration. It depends on the shared constants/hooks/propel/services/types/ui/utils packages and, per the root graph, depends on the API and web apps at runtime.
- **Serving**: `Dockerfile.admin` serves the static client from `/god-mode` via nginx on port 3000.

## Space — `apps/space/`

- **Manifest/entry**: [`package.json`](../../apps/space/package.json) (`name: "space"`, `react-router dev --port 3002`), [`app/routes.ts`](../../apps/space/app/routes.ts) (index, `:workspaceSlug/:projectId`, `issues/:anchor`), [`Dockerfile.space`](../../apps/space/Dockerfile.space).
- **Responsibility**: public project-space pages — a read/limited-view frontend keyed by workspace slug and project id, with issue pages by anchor. Consumes shared packages (constants, editor, i18n, propel, services, types, ui, utils) and depends on the API and web apps at runtime (root graph).
- **Serving**: unlike web/admin, `Dockerfile.space` runs an SSR server (`npx react-router-serve ./build/server/index.js`) on port 3000, health-checked at `/spaces/`.

## Live — `apps/live/`

- **Manifest/entry**: [`package.json`](../../apps/live/package.json) (description: "A realtime collaborative server powers Plane's rich text editor", `main: ./dist/start.mjs`), [`src/server.ts`](../../apps/live/src/server.ts), [`src/hocuspocus.ts`](../../apps/live/src/hocuspocus.ts), [`Dockerfile.live`](../../apps/live/Dockerfile.live).
- **Responsibility**: the realtime collaboration backend. It is an Express server (helmet, compression, CORS, logging) that mounts a Hocuspocus server for collaborative rich-text editing, plus controllers for document collaboration, PDF export, and health checks (`apps/live/src/controllers/`). Environment is validated with a zod schema ([`src/env.ts`](../../apps/live/src/env.ts): `API_BASE_URL`, `LIVE_SERVER_SECRET_KEY`, `REDIS_*`, `CORS_ALLOWED_ORIGINS`, etc.). Depends on `@plane/editor`, `@plane/types`, `@plane/utils`, `@plane/decorators`, and `@plane/logger` (manifest `dependencies`).
- **Runtime deps**: Redis (`src/redis.ts`); the compose stack runs `live` without a hard dependency on api ([`docker-compose.yml`](../../docker-compose.yml)).

## Proxy — `apps/proxy/`

- **Manifest/entry**: no `package.json` (excluded from the pnpm workspace and from Turbo). [`Dockerfile.ce`](../../apps/proxy/Dockerfile.ce) builds a Caddy image with DNS/security modules; [`Caddyfile.ce`](../../apps/proxy/Caddyfile.ce) is the routing config.
- **Responsibility**: the reverse proxy that fronts the other services. `Caddyfile.ce` routes:
  - `/spaces/*` → `space:3000`
  - `/god-mode/*` → `admin:3000`
  - `/live/*` → `live:3000`
  - `/api/*`, `/auth/*`, `/static/*` → `api:8000`
  - `/{$BUCKET_NAME}/*` → `plane-minio:9000`
  - `/*` → `web:3000`
- **Compose**: `proxy` publishes ports `${LISTEN_HTTP_PORT}:80` and `${LISTEN_HTTPS_PORT}:443` and depends on web, api, space, admin ([`docker-compose.yml`](../../docker-compose.yml)). A second config, `Caddyfile.aio.ce`, targets the all-in-one deployment variant.

## Where to look next

- [Backend (API)](./backend.md) — the Django project behind the api application.
- [Frontend](./frontend.md) — how web/admin/space/live compose and share packages.
- [Operations](./operations.md) — Dockerfiles, compose services, and image-building CI.
- [Packages](./packages.md) — the shared `@plane/*` packages these apps consume.
