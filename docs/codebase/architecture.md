# Repository Architecture

This page describes the top-level architecture of the Plane monorepo as declared by its root manifests, compose files, and the repository architecture-landscape graph. It distinguishes the root graph (a landscape view) from scoped implementation graphs.

## Monorepo and workspace topology

Plane is a pnpm + Turbo monorepo. The root [`package.json`](../../package.json) declares the project (`name: "plane"`, version `1.3.1`, `private: true`, AGPL-3.0), pins `packageManager: pnpm@11.3.0` and `engines.node >= 22.18.0`, and exposes Turbo-driven scripts:

- `dev`, `build`, `start`, `clean`
- `check` (format + lint + types), `check:format`, `check:lint`, `check:types`
- `fix`, `fix:format`, `fix:lint`
- `prepare` (runs `husky`) and `doctor`

[`pnpm-workspace.yaml`](../../pnpm-workspace.yaml) defines the workspace as `apps/*` and `packages/*`, with two explicit exclusions: `!apps/api` and `!apps/proxy`. The API is a Python/Django application (not a Node package), and the proxy is a Caddy container without a `package.json` — both are managed outside the pnpm workspace. The `catalog:` block centralizes external dependency versions, and `overrides` pins transitive resolutions.

[`turbo.json`](../../turbo.json) defines the task pipeline (`build`, `dev`, `check*`, `fix*`, `test`, `start`, `clean`, `build-storybook`) and the global environment variables shared across workspace tasks (all `VITE_*` frontend base-URL/path variables, `SENTRY_*`, `LOG_LEVEL`, `NODE_ENV`, `APP_VERSION`, `DEV`). Remote caching is disabled (`remoteCache.enabled: false`).

## System layers

The repository architecture landscape graph ([`../../.ua/knowledge-graph.json`](../../.ua/knowledge-graph.json)) organizes the repository into three layers:

| Layer | Contents | Source evidence |
| --- | --- | --- |
| Workspace & Applications | Monorepo root, `package.json`, `pnpm-workspace.yaml`, `turbo.json`, and the five deployable applications: api, web, admin, space, live | [`pnpm-workspace.yaml`](../../pnpm-workspace.yaml), [`turbo.json`](../../turbo.json), `apps/*/package.json` |
| Shared Packages | Nine principal `@plane/*` packages forming the dependency backbone (leaf `types` up to `ui`/`editor` layers) | `packages/*/package.json` — see [packages.md](./packages.md) for the full tracked list |
| Infrastructure & Coordination Boundaries | `docker-compose.yml`, `deployments/` self-hosting recipes, `.github/workflows/` CI/CD pipelines | [`docker-compose.yml`](../../docker-compose.yml), [`deployments/`](../../deployments/), [`.github/workflows/`](../../.github/workflows/) |

The graph's project metadata (`project.frameworks`) records Django, React Router, and Node.js as the three frameworks, which matches the manifest evidence: `apps/api` is Django (see [backend.md](./backend.md)), the web/admin/space frontends are React Router apps (see [frontend.md](./frontend.md)), and `apps/live` is a Node.js/Hocuspocus server.

## Applications at a glance

| Application | Path | Manifest / entry | Runtime role |
| --- | --- | --- | --- |
| api | `apps/api/` | [`manage.py`](../../apps/api/manage.py), [`Dockerfile.api`](../../apps/api/Dockerfile.api) | Django/DRF backend; excluded from the pnpm workspace |
| web | `apps/web/` | [`package.json`](../../apps/web/package.json), [`app/routes.ts`](../../apps/web/app/routes.ts) | Main React Router SPA (port 3000) |
| admin | `apps/admin/` | [`package.json`](../../apps/admin/package.json), [`app/routes.ts`](../../apps/admin/app/routes.ts) | Instance administration UI (port 3001, god-mode) |
| space | `apps/space/` | [`package.json`](../../apps/space/package.json), [`app/routes.ts`](../../apps/space/app/routes.ts) | Public project-space app (port 3002) |
| live | `apps/live/` | [`package.json`](../../apps/live/package.json), [`src/start.ts`](../../apps/live/src/start.ts) | Realtime collaborative editing server (Hocuspocus/Express) |
| proxy | `apps/proxy/` | [`Dockerfile.ce`](../../apps/proxy/Dockerfile.ce), [`Caddyfile.ce`](../../apps/proxy/Caddyfile.ce) | Caddy reverse proxy; no package.json, outside the workspace |

Detailed, per-application source-backed subsections are on [applications.md](./applications.md).

## What the root graph represents vs. implementation graphs

- **Root graph** ([`../../.ua/knowledge-graph.json`](../../.ua/knowledge-graph.json)): a top-level *landscape* of 28 analyzed files (per [`../../.ua/meta.json`](../../.ua/meta.json)). It records module boundaries (`contains`), package dependency edges (`depends_on`), and deployment relationships (`deploys`/`configures`). It deliberately does not describe component behavior.
- **Implementation graphs**: bounded, per-scope graphs such as the URL Routing Pilot ([`../../apps/api/plane/app/urls/.ua/knowledge-graph.json`](../../apps/api/plane/app/urls/.ua/knowledge-graph.json)), which detail a subsystem's files, classes, and import/export relationships. These are the authoritative source for component-level detail within their scope.

The [graph roadmap](./graph-roadmap.md) defines the planned four-layer hierarchy (repository map → application graphs → package graphs → domain deep dives) and the rule that whole-codebase coverage must not be claimed until the repository map and every planned component scope are generated and reviewed.

## Operational / config boundaries

- **Container orchestration**: [`docker-compose.yml`](../../docker-compose.yml) (production-style full stack incl. proxy on ports 80/443), [`docker-compose-local.yml`](../../docker-compose-local.yml) (local dev dependencies + api), [`docker-compose-test.yml`](../../docker-compose-test.yml) (isolated API test stack). See [operations.md](./operations.md).
- **Self-hosting recipes**: `deployments/` (`cli`, `swarm`, `kubernetes`, `aio`).
- **CI/CD**: `.github/workflows/` — build/lint/type pipelines, image builds, CodeQL, feature previews. See [operations.md](./operations.md).
- **Secrets/env**: per-app `.env` files generated by [`setup.sh`](../../setup.sh) from `.env.example` templates; never committed. See [testing-and-contributing.md](./testing-and-contributing.md) for setup.

## Where to look next

- [Applications](./applications.md) — per-app manifests, entry points, and responsibilities.
- [Backend (API)](./backend.md) — Django project structure and the URL-routing pilot.
- [Frontend](./frontend.md) — how the frontend applications and packages compose.
- [Packages](./packages.md) — the full workspace package inventory.
