# Domains and Integrations

Cross-cutting domains and integrations that can be supported by source or by existing documentation. This page separates **confirmed implementation areas** (verifiable from source/manifests) from **future deep-dive candidates** (documented domains that lack a dedicated graph or analysis page). It links to the existing GitHub integration docs instead of duplicating them.

## Confirmed implementation areas

### GitHub integration (native GitHub App)

The most fully documented cross-cutting domain. Source evidence spans the backend and the frontends:

- **Backend**: `plane.app.urls.github_sync` (routes: repository mappings, issue links, branch creation, webhooks, installations, repositories — per the URL Routing Pilot graph [`../../apps/api/plane/app/urls/.ua/knowledge-graph.json`](../../apps/api/plane/app/urls/.ua/knowledge-graph.json)); `plane.app.views.github_sync.py` and `plane.app.serializers.github_sync.py`; models `plane/db/models/integration/github_app.py`, `github.py`, `github_sync.py`; services `plane/services/github/client.py` and `credentials.py`; instance-level configuration in `plane/license/` (`api/views/github_app.py`, `configuration.py`, `urls.py` GitHub App endpoints).
- **Frontends**: web settings routes for GitHub (`:workspaceSlug/settings/github`, `:workspaceSlug/settings/projects/:projectId/github` — [`apps/web/app/routes/core.ts`](../../apps/web/app/routes/core.ts)); admin god-mode `github-app` route ([`apps/admin/app/routes.ts`](../../apps/admin/app/routes.ts)).
- **CI**: `.github/workflows/test-github-app-configuration.yml` runs the GitHub App configuration contract tests.
- **Docs**: the complete feature documentation set is at [../github-integration/README.md](../github-integration/README.md) (administrator setup, PR linking, operations & troubleshooting, developer guide). This page intentionally does not duplicate it.

### Authentication

Cross-cutting by nature: web, admin, and space all authenticate against the API. Source evidence:

- `plane/authentication/urls.py` — sign-in/sign-up, OAuth (Google, GitHub, GitLab, Gitea) with app and space variants, magic-link (`magic-generate/sign-in/sign-up`), password reset/set/change, CSRF token, email check ([`apps/api/plane/authentication/urls.py`](../../apps/api/plane/authentication/urls.py)).
- Frontend OAuth helpers exist in web, space, and admin (`hooks/oauth/`, `helpers/authentication.helper.tsx`, admin `components/authentication/` with per-provider config cards).
- Admin `authentication` route group with provider pages ([`apps/admin/app/routes.ts`](../../apps/admin/app/routes.ts)).
- Status: `Planned deep dive` — no dedicated graph or analysis page yet.

### Realtime collaboration (live)

`apps/live` is a standalone realtime backend used by the editor:

- Express + Hocuspocus server ([`apps/live/src/hocuspocus.ts`](../../apps/live/src/hocuspocus.ts)) with Redis persistence, auth via `onAuthenticate` ([`src/lib/auth.ts`](../../apps/live/src/lib/auth.ts)), and controllers for document collaboration and PDF export ([`src/controllers/`](../../apps/live/src/controllers/)).
- Consumed by `@plane/editor`-based editing in web/space; proxied at `/live/*` by Caddy ([`apps/proxy/Caddyfile.ce`](../../apps/proxy/Caddyfile.ce)).
- Status: `Planned deep dive` — architecture described in [applications.md](./applications.md#live--apps-live) and [frontend.md](./frontend.md), no dedicated graph.

### Internationalization (i18n)

Cross-cutting across web and space:

- `@plane/i18n` package with per-language `translations.json` and ICU plural support ([`packages/i18n/`](../../packages/i18n/)); contributing guide in [`CONTRIBUTING.md`](../../CONTRIBUTING.md) (translation structure, adding languages).
- CI enforces locale sync: `.github/workflows/i18n-sync-check.yml` runs `packages/i18n/scripts/sync-check.ts --ci`.
- Status: `Confirmed` as a documented cross-cutting domain; graph-level dive `Planned`.

## Future deep-dive candidates (documented, not yet graphed)

These domains are visible in source but have no dedicated graph or analysis page yet; each is a candidate for the [domain deep-dive layer](./graph-roadmap.md#domain-deep-dives).

| Domain | Where it shows up | Notes |
| --- | --- | --- |
| Work-item (issue) lifecycle | `plane/app/views/issue/` (base, comment, attachment, relation, label, activity, version, archive, reaction, subscriber, link), `plane/app/urls/issue.py`, `plane/api/urls/work_item.py` | Core domain; route-level graph exists only for `plane.app.urls` |
| Project/workspace management | `plane/app/views/project/`, `workspace/`; `plane/app/urls/project.py`, `workspace.py` | Included in URL pilot scope, no dedicated graph |
| Cycles & modules | `plane/app/views/cycle/`, `module/`; `plane/api/views/cycle.py`, `module.py` | Planned |
| Webhooks & API tokens | `plane/app/views/webhook/`, `plane/app/views/api.py`, `plane/db/models/webhook.py`, `api.py` | Includes webhook IP/host allowlisting in `settings/common.py` |
| Export / analytics | `plane/app/views/exporter/`, `analytic/`; bgtasks `export_task.py`, `analytic_plot_export.py` | Planned |
| Notifications & email | `plane/bgtasks/notification_task.py`, `email_notification_task.py`, `plane/app/views/notification/` | Celery-driven; retention config in `settings/common.py` |
| Time tracking | `plane/api/views/time_tracking.py`, `plane/db/models/time_tracking.py`, `plane/api/urls/time_tracking.py` | Has dedicated CI regression tests (`.github/workflows/test-auto-state-duration.yml`) |
| Object storage / assets | `plane/app/views/asset/`, `plane/api/views/asset.py`, `plane/settings/storage.py` (S3/MinIO presigned URLs) | Cross-cuts API, live (PDF export), and MinIO in compose |
| AI assistant | `plane/app/views/external/` (AI endpoints), `plane/app/urls/external.py`, `@plane` AI constants (`packages/constants/src/ai.ts`) | `Planned` |

## Guidelines for these pages

- Feature documentation (e.g. GitHub integration) lives under [../github-integration/](../github-integration/); codebase-understanding pages link to it rather than restating it.
- A domain becomes "confirmed" here only when the claim is backed by a manifest, route, view, model, or workflow path listed above; everything else is marked `Planned` / `Not yet documented`.

## Where to look next

- [Backend (API)](./backend.md) — the apps and URL packages these domains live in.
- [Graph roadmap](./graph-roadmap.md#domain-deep-dives) — the planned deep-dive layer.
- [GitHub integration](../github-integration/README.md) — the one fully documented integration.
