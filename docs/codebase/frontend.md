# Frontend

This page covers how the frontend applications compose in the Plane monorepo, how web/admin/space/live relate where source and manifests confirm it, the shared package roles they build on, and practical development navigation. It is development navigation, not a framework tutorial.

## Application composition

All three UI applications — web, admin, space — are React Router apps built with Vite, and the live server is a Node.js/Hocuspocus realtime backend used by the editor. Evidence: each of `apps/web`, `apps/admin`, and `apps/space` declares `react-router`, `react`, `react-dom`, `vite` (`catalog:`), and a `react-router dev --port <n>` dev script in its [`package.json`](../../apps/web/package.json). `apps/live` declares `express`, `@hocuspocus/*`, `yjs`, and a `tsdown` build ([`apps/live/package.json`](../../apps/live/package.json)).

| App   | Port (dev) | Entry / routes                                                                                                                           | Rendering mode                                                                                                                                                                                                    |
| ----- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| web   | 3000       | [`app/routes.ts`](../../apps/web/app/routes.ts) → merges `routes/core.ts` + `routes/extended.ts`; catch-all 404                          | SPA (`ssr: false` in [`react-router.config.ts`](../../apps/web/react-router.config.ts)), served by Caddy ([`Dockerfile.web`](../../apps/web/Dockerfile.web), [`caddy/Caddyfile`](../../apps/web/caddy/Caddyfile)) |
| admin | 3001       | [`app/routes.ts`](../../apps/admin/app/routes.ts) — instance settings (general, workspace, email, authentication, ai, image, github-app) | SPA, served at `/god-mode` by Caddy ([`Dockerfile.admin`](../../apps/admin/Dockerfile.admin), [`caddy/Caddyfile`](../../apps/admin/caddy/Caddyfile))                                                              |
| space | 3002       | [`app/routes.ts`](../../apps/space/app/routes.ts) — index, `:workspaceSlug/:projectId`, `issues/:anchor`                                 | SSR via `react-router-serve` ([`Dockerfile.space`](../../apps/space/Dockerfile.space))                                                                                                                            |
| live  | 3000       | [`src/server.ts`](../../apps/live/src/server.ts) + `src/controllers/`                                                                    | Node/Express + Hocuspocus websocket server ([`src/hocuspocus.ts`](../../apps/live/src/hocuspocus.ts))                                                                                                             |

How they relate (verified from manifests and the root graph):

- **web** depends on blocks, constants, editor, hooks, i18n, services, shared-state, types, utils and the npm `@makeplane/propel` ([`apps/web/package.json`](../../apps/web/package.json)).
- **admin** depends on blocks, constants, hooks, i18n, services, types, utils and the npm `@makeplane/propel` ([`apps/admin/package.json`](../../apps/admin/package.json)).
- **space** depends on blocks, constants, editor, i18n, services, types, utils and the npm `@makeplane/propel` ([`apps/space/package.json`](../../apps/space/package.json)).
- **live** depends on decorators, editor, logger, types, utils ([`apps/live/package.json`](../../apps/live/package.json)).
- The root graph ([`../../.ua/knowledge-graph.json`](../../.ua/knowledge-graph.json)) records runtime `depends_on` edges: web → api, admin → api and web, space → api and web. The proxy routes traffic to space/admin/live/api/web and MinIO ([`apps/proxy/Caddyfile.ce`](../../apps/proxy/Caddyfile.ce)), so the frontends are served behind Caddy in the compose stack.
- Build-time env wiring is shared across web/admin/space Dockerfiles via `VITE_API_BASE_URL`, `VITE_WEB_BASE_URL`, `VITE_ADMIN_BASE_URL/PATH`, `VITE_SPACE_BASE_URL/PATH`, `VITE_LIVE_BASE_URL/PATH` (see [`apps/web/Dockerfile.web`](../../apps/web/Dockerfile.web) and [`turbo.json`](../../turbo.json) `globalEnv`).

## Shared package roles (summary)

The frontends build on shared `@plane/*` packages; full details are in [packages.md](./packages.md).

- **UI & components**: primitives (menus, dialogs, tooltips, avatar, charts, icons) come from the published npm package `@makeplane/propel` (`@makeplane/propel/components/*`, `elements/*`, `icons`); composite/Plane-specific components live in `@plane/blocks` (`packages/blocks`, subpath imports only, e.g. `@plane/blocks/toast`). There is no `packages/ui` or `packages/propel`.
- **Editor**: `@plane/editor` — the core rich-text editor (Tiptap/ProseMirror) used by web, space, and the live server.
- **State**: `@plane/shared-state` (MobX stores) used by web.
- **Services**: `@plane/services` (axios API layer) used by web, admin, and space.
- **i18n**: `@plane/i18n` (i18next, per-language `locales/*/translations.json`) used by web and space.
- **Foundations**: `@plane/types` (types), `@plane/constants`, `@plane/utils` (helpers), `@plane/hooks` (React hooks), plus dev-time `@plane/tailwind-config` and `@plane/typescript-config`.

## Development navigation

- **Start dev servers**: `pnpm dev` runs `turbo run dev --concurrency=18` ([`package.json`](../../package.json)) — web on 3000, admin on 3001, space on 3002, live on 3000 (via `tsdown --watch --onSuccess "node ."`).
- **Local backend**: the Django API runs in Docker via `docker compose -f docker-compose-local.yml up` (see [testing-and-contributing.md](./testing-and-contributing.md#setup) and [operations.md](./operations.md#local-development-stack)); the frontends call it via `VITE_API_BASE_URL`.
- **Per-app checks**: each frontend app exposes `check:lint`, `check:types`, `check:format`, `fix:*` scripts. `check:types` runs `react-router typegen && tsc --noEmit`.
- **Storybook**: none in the repo; the Storybook configs were removed with `packages/ui` and `packages/propel` in v1.5.0.
- **Route registration**: web merges core + extended route tables in `app/routes.ts`; admin and space define flat route arrays. New pages follow the existing `route(...)`/`layout(...)`/`index(...)` helpers from `@react-router/dev/routes`.

## Not yet documented

- Component-level detail per app is `Planned` (application graphs pending per [graph-roadmap.md](./graph-roadmap.md#application-graphs)); only the app shells and route trees are described here.
- The `apps/web` "extended" route set (EE-flavored additions in `app/routes/extended.ts`) is not individually inventoried here.

## Where to look next

- [Applications](./applications.md) — per-app manifests, Dockerfiles, and serving modes.
- [Packages](./packages.md) — the full shared-package inventory with roles.
- [Backend (API)](./backend.md) — the API the frontends call.
- [Operations](./operations.md) — how frontend images are built and deployed.
