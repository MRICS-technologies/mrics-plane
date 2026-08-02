# Backend (API)

This page documents the Django/API architecture as verified from `apps/api` source and configuration. It also explains the completed URL-routing pilot and its knowledge graph, and gives extension/testing guidance grounded in the repository's own configuration.

## Project entry points

| Entry | Path | Role |
| --- | --- | --- |
| Django project root | [`apps/api/plane/`](../../apps/api/plane/) | The `plane` Django project package |
| Management entry | [`manage.py`](../../apps/api/manage.py) | Defaults `DJANGO_SETTINGS_MODULE` to `plane.settings.production` |
| WSGI/ASGI | [`wsgi.py`](../../apps/api/plane/wsgi.py), [`asgi.py`](../../apps/api/plane/asgi.py) | Both default to `plane.settings.production`; ASGI uses `channels` `ProtocolTypeRouter` with HTTP only |
| Celery | [`celery.py`](../../apps/api/plane/celery.py) | `Celery("plane")` app, `config_from_object("django.conf:settings", namespace="CELERY")`, `autodiscover_tasks()`, `django_celery_beat.schedulers.DatabaseScheduler`, and a `beat_schedule` of recurring jobs |
| Requirements | [`requirements/base.txt`](../../apps/api/requirements/base.txt) (Django 4.2, DRF 3.15, celery 5.4, channels, uvicorn, drf-spectacular, etc.), `local.txt`, `test.txt`, `production.txt` | Split by environment; `requirements.txt` is a PaaS-compat shim to `production.txt` |
| Runtime entry scripts | [`apps/api/bin/`](../../apps/api/bin/) | `docker-entrypoint-api.sh` (gunicorn + `plane.asgi`), `worker.sh`, `beat.sh`, `migrator.sh`, `api-local.sh` |

## Settings topology

[`plane/settings/`](../../apps/api/plane/settings/) provides five modules all rooted in `common.py`:

- `common.py` — base settings: installed apps, middleware, DRF defaults (session auth, `IsAuthenticated`, throttle rates), Postgres via `DATABASE_URL` or `POSTGRES_*` vars, Redis cache (`REDIS_URL`), Celery/RabbitMQ broker, S3/MinIO storage (`USE_MINIO`), CORS, and app base URLs (`APP_BASE_PATH=/`, `ADMIN_BASE_PATH=/god-mode/`, `SPACE_BASE_PATH=/spaces/`, `LIVE_BASE_PATH=/live/`).
- `local.py` — dev: `DEBUG=True`, debug-toolbar, console email backend, JSON console logging.
- `production.py` — prod: gunicorn, `scout_apm`, file+console JSON logging, `SECURE_PROXY_SSL_HEADER`.
- `test.py` — test: `DEBUG=True`, locmem email backend, adds `plane.tests` to installed apps.
- Supporting modules: `redis.py` (client factory), `storage.py` (S3/MinIO presigned-URL storage), `openapi.py` (drf-spectacular settings, used when `ENABLE_DRF_SPECTACULAR=1`).

## URL-routing topology

[`plane/urls.py`](../../apps/api/plane/urls.py) is the root URLconf. It includes:

| Mount | Included module | Domain |
| --- | --- | --- |
| `api/` | `plane.app.urls` | Main application API (work items, projects, workspaces, cycles, modules, pages, views, webhooks, GitHub sync, …) |
| `api/public/` | `plane.space.urls` | Public project-space API (`apps/api/plane/space/urls/`) |
| `api/instances/` | `plane.license.urls` | Instance/god-mode administration incl. GitHub App configuration |
| `api/v1/` | `plane.api.urls` | Versioned API (`apps/api/plane/api/urls/`) |
| `auth/` | `plane.authentication.urls` | Sign-in/up, OAuth (Google/GitHub/GitLab/Gitea), magic link, passwords |
| `""` | `plane.web.urls` | `robots.txt` and a health-check view |
| `api/schema/` (+ swagger/redoc) | drf-spectacular | Only when `ENABLE_DRF_SPECTACULAR=1` |
| `__debug__/` | debug-toolbar | Only when `DEBUG` and toolbar importable |

### The URL Routing Pilot

The **completed** pilot graph covers the main application routing package `apps/api/plane/app/urls/`:

- Artifact: [`apps/api/plane/app/urls/.ua/knowledge-graph.json`](../../apps/api/plane/app/urls/.ua/knowledge-graph.json)
- Scope: the 22-file subsystem under `apps/api/plane/app/urls/` — 22 file nodes + 1 class node (`WorkItemStateDurationAppEndpoint` in `issue.py`) = 23 nodes, 23 edges, 2 layers, 3 guided-tour steps (metrics per [graph-roadmap.md](./graph-roadmap.md#completed)).
- Topology: [`__init__.py`](../../apps/api/plane/app/urls/__init__.py) imports each domain module's `urlpatterns` (analytic, api, asset, cycle, estimate, external, github_sync, intake, issue, module, notification, page, project, search, state, timezone, user, views, webhook, workspace, exporter) and flattens them into the package `urlpatterns`. The graph's two layers are "Routing Composition" (`__init__.py`) and "Domain Route Definitions" (the 21 domain modules).

This is a **bounded subsystem graph**, not a whole-codebase graph. The `plane.api.urls`, `plane.space.urls`, `plane.license.urls`, and `plane.authentication.urls` packages are not yet graphed.

## App boundaries (verified)

`INSTALLED_APPS` in [`settings/common.py`](../../apps/api/plane/settings/common.py) registers the in-house apps below:

| Django app | Source dir | Verified responsibility |
| --- | --- | --- |
| `plane.app` | [`plane/app/`](../../apps/api/plane/app/) | Main API: `views/` (issue, project, workspace, cycle, module, page, state, view, search, asset, webhook, notification, intake, estimate, exporter, analytic, external, github_sync, user, timezone, api), `serializers/`, `urls/`, `permissions/`, `middleware/` |
| `plane.api` | [`plane/api/`](../../apps/api/plane/api/) | Versioned v1 API: `urls/` (asset, cycle, estimate, intake, invite, label, member, module, project, schema, state, sticky, time_tracking, user, work_item), `views/`, `serializers/`, `middleware/`, `rate_limit.py` |
| `plane.space` | [`plane/space/`](../../apps/api/plane/space/) | Public space API: `urls/` (asset, intake, issue, project) |
| `plane.license` | [`plane/license/`](../../apps/api/plane/license/) | Instance administration: `urls.py` + `api/views/` (admin, base, configuration, github_app, instance, workspace) |
| `plane.authentication` | [`plane/authentication/`](../../apps/api/plane/authentication/) | Authentication endpoints, `session.py`, `rate_limit.py`, `urls.py` |
| `plane.db` | [`plane/db/`](../../apps/api/plane/db/) | Models (`db/models/`: user, workspace, project, issue, cycle, module, state, label, estimate, view, page, webhook, api, intake, integration/* incl. `github_app.py` and `github_sync.py`, time_tracking, …), `mixins.py`, and the session model used by `SESSION_ENGINE` |
| `plane.bgtasks` | [`plane/bgtasks/`](../../apps/api/plane/bgtasks/) | Celery background tasks: notification, email, exporter, file asset, issue automation, webhook, cleanup, deletion, page/issue version sync, workspace seed, etc. |
| `plane.utils` | [`plane/utils/`](../../apps/api/plane/utils/) | Helpers: email, cache, CSV, markdown, pagination, grouper, URL/security helpers, error codes, logging, etc. |
| `plane.middleware` | [`plane/middleware/`](../../apps/api/plane/middleware/) | `db_routing.py`, `logger.py`, `request_body_size.py` |
| `plane.analytics` | [`plane/analytics/`](../../apps/api/plane/analytics/) | Analytics app |
| `plane.web` | [`plane/web/`](../../apps/api/plane/web/) | `robots.txt` + health-check views (`views.py`, `urls.py`) |

Note: `plane.tests` is not in `common.INSTALLED_APPS`; it is added by [`settings/test.py`](../../apps/api/plane/settings/test.py).

## Task / background boundaries

- **Celery worker + beat** run as separate compose services (`worker`, `beat-worker`) built from the same `Dockerfile.api` ([`docker-compose.yml`](../../docker-compose.yml)).
- The **beat schedule** is defined in [`celery.py`](../../apps/api/plane/celery.py): e.g. email notification stack every 5 minutes, daily hard-delete / archive-and-close / exporter / file-asset / api-log / webhook-log / page-version / issue-description-version cleanup jobs, and an instance-metrics push interval.
- **Task modules** live in `plane/bgtasks/` and are also listed in `CELERY_IMPORTS` ([`settings/common.py`](../../apps/api/plane/settings/common.py)).
- Not every task is individually analyzed; task-level deep dives are `Planned` (see [domains-and-integrations.md](./domains-and-integrations.md)).

## Extension & testing guidance (grounded in repo config)

- **Ruff lint**: [`pyproject.toml`](../../apps/api/pyproject.toml) configures `ruff` (E/F, isort, pydocstyle google convention, line-length 120, migrations excluded). CI runs `ruff check --fix apps/api` ([`.github/workflows/pull-request-build-lint-api.yml`](../../.github/workflows/pull-request-build-lint-api.yml)).
- **pytest**: [`pytest.ini`](../../apps/api/pytest.ini) sets `DJANGO_SETTINGS_MODULE = plane.settings.test`, `--reuse-db --nomigrations`, and defines markers `unit`, `contract`, `smoke`, `slow` (strict). Test layout: `plane/tests/` with `unit/`, `contract/app/`, `contract/api/`, `smoke/`; factories in `plane/tests/factories.py`.
- **Running the suite**: use the isolated Docker stack [`docker-compose-test.yml`](../../docker-compose-test.yml) (Postgres/Valkey/RabbitMQ/MinIO with health checks, tmpfs data). Full walkthrough: [`apps/api/tests/RUNNING_TESTS.md`](../../apps/api/tests/RUNNING_TESTS.md); conventions: [`apps/api/plane/tests/TESTING_GUIDE.md`](../../apps/api/plane/tests/TESTING_GUIDE.md). Summary on [testing-and-contributing.md](./testing-and-contributing.md).
- **Specialized CI**: `.github/workflows/test-auto-state-duration.yml` (time-tracking regression) and `.github/workflows/test-github-app-configuration.yml` (GitHub App configuration contract tests) run targeted pytest subsets with GitHub-hosted Postgres/Redis services.
- **Adding an endpoint**: follow the existing pattern — a `urlpatterns` list in `plane/app/urls/` (or a v1 module under `plane/api/urls/`), a view/viewset under `plane/app/views/`, a serializer under `plane/app/serializers/`, and a model under `plane/db/models/`; register the app if new. This mirrors how the URL-routing pilot modules compose into `plane/app/urls/__init__.py`.

## Not yet documented / planned deep dives

- Full views/serializers/models inventory per domain: `Planned` (application/domain graphs pending per [graph-roadmap.md](./graph-roadmap.md)).
- `plane.api` (v1), `plane.space`, `plane.license`, `plane.authentication` URL packages: `Planned` — only `plane.app.urls` has a completed graph.
- Domain deep-dive candidate: GitHub integration backend (already documented as a feature in [../github-integration/README.md](../github-integration/README.md), graph-level dive `Planned`).

## Where to look next

- [Applications](./applications.md) — api application entry points and runtime processes.
- [Domains and integrations](./domains-and-integrations.md) — cross-cutting backend domains.
- [Testing and contributing](./testing-and-contributing.md) — how to run and validate changes.
- [Graph roadmap](./graph-roadmap.md) — status of planned backend graphs.
