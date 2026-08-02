# Operations

A *configuration map* of the developer, CI, container, and deployment surface of the repository, based on compose files, root scripts, `deployments/`, and `.github/`. It describes what is configured and where — it does not describe live environments, credentials, or production state, and it does not include operational commands that require secrets.

## Local development stack

- **`setup.sh`** ([`setup.sh`](../../setup.sh)) — copies `.env.example` → `.env` for root, web, api, space, admin, and live; generates a Django `SECRET_KEY` into `apps/api/.env`; enables corepack pnpm and runs `pnpm install`.
- **`docker-compose-local.yml`** ([`docker-compose-local.yml`](../../docker-compose-local.yml)) — the local *dependencies* stack: `plane-db` (Postgres 15.7-alpine), `plane-redis` (Valkey 7.2.11-alpine), `plane-mq` (RabbitMQ 3.13.6), `plane-minio` (MinIO with a bootstrap bucket), plus the `api` service (built from `apps/api/Dockerfile.dev`, runs `docker-entrypoint-api-local.sh` → `runserver` on 8000), `worker`, `beat-worker`, and `migrator`. Ports exposed: 5432, 6379, 8000, 9000, 9090. Web/admin/space run via `pnpm dev` on the host (see [testing-and-contributing.md](./testing-and-contributing.md#setup)).
- **`docker-compose.yml`** ([`docker-compose.yml`](../../docker-compose.yml)) — the full service stack used for a production-style deployment: web, admin, space, api, worker, beat-worker, migrator, live, plane-db, plane-redis, plane-mq, plane-minio, and `proxy` (Caddy, publishing `${LISTEN_HTTP_PORT}:80` and `${LISTEN_HTTPS_PORT}:443`). The API/worker/beat/migrator share `Dockerfile.api` with different entry scripts; frontends use their own Dockerfiles.
- **`docker-compose-test.yml`** ([`docker-compose-test.yml`](../../docker-compose-test.yml)) — isolated API test stack (`test-db`, `test-redis`, `test-mq`, `test-minio`, `api-tests` with health-check gates and tmpfs data dirs). See [testing-and-contributing.md](./testing-and-contributing.md#api-tests).

## Container images

| Image | Dockerfile | Runtime entry |
| --- | --- | --- |
| web | [`apps/web/Dockerfile.web`](../../apps/web/Dockerfile.web) | nginx on 3000 serving the static client |
| admin | [`apps/admin/Dockerfile.admin`](../../apps/admin/Dockerfile.admin) | nginx on 3000 serving `/god-mode` |
| space | [`apps/space/Dockerfile.space`](../../apps/space/Dockerfile.space) | `react-router-serve` on 3000 (SSR) |
| live | [`apps/live/Dockerfile.live`](../../apps/live/Dockerfile.live) | `node apps/live` (dist build) |
| api | [`apps/api/Dockerfile.api`](../../apps/api/Dockerfile.api) | entry scripts in `apps/api/bin/` (api/worker/beat/migrator) |
| proxy | [`apps/proxy/Dockerfile.ce`](../../apps/proxy/Dockerfile.ce) | Caddy with [`Caddyfile.ce`](../../apps/proxy/Caddyfile.ce) |

All frontend Dockerfiles follow the same multi-stage pattern: `turbo prune --scope=<app> --docker` → `pnpm fetch`/`install --offline --frozen-lockfile` → `turbo run build --filter=<app>`, with build-time `VITE_*` args.

## Self-hosting deployment recipes

`deployments/` contains the packaged self-hosting recipes (structure only, not live state):

- [`deployments/cli/`](../../deployments/cli/) — Docker Compose CLI setup (community image, `install.sh`/`setup.sh` referenced by `build-branch.yml`).
- [`deployments/swarm/`](../../deployments/swarm/) — Docker Swarm stack (`swarm.sh` uploaded as a release asset).
- [`deployments/kubernetes/`](../../deployments/kubernetes/) — Helm chart used by feature-preview deployments.
- [`deployments/aio/`](../../deployments/aio/) — all-in-one community image (built by `feature-deployment.yml` via `aio/Dockerfile-app`, and by `build-branch.yml` via `deployments/aio/community/`).

The root graph records `deployments/` as a single module with `deploys` edges to all five applications ([`../../.ua/knowledge-graph.json`](../../.ua/knowledge-graph.json)).

## CI/CD pipelines (`.github/workflows/`)

| Workflow | Trigger | What it does |
| --- | --- | --- |
| [`pull-request-build-lint-web-apps.yml`](../../.github/workflows/pull-request-build-lint-web-apps.yml) | PR to `preview` (non-draft, review requested) | Turbo `check:format`, `build --affected`, `check:lint`, `check:types --affected` for the web apps/workspace |
| [`pull-request-build-lint-api.yml`](../../.github/workflows/pull-request-build-lint-api.yml) | PR to `preview` touching `apps/api/**` | `pip install -r requirements.txt` + `ruff check --fix apps/api` |
| [`copyright-check.yml`](../../.github/workflows/copyright-check.yml) | PR to `preview` | `addlicense -check -f COPYRIGHT.txt` on tracked `.py`/`.ts`/`.tsx` files |
| [`i18n-sync-check.yml`](../../.github/workflows/i18n-sync-check.yml) | PR/push touching `packages/i18n/**` | `pnpm dlx tsx packages/i18n/scripts/sync-check.ts --ci` |
| [`react-doctor.yml`](../../.github/workflows/react-doctor.yml) | PR (opened/synchronize/reopened/ready) + push to `main` | React Doctor scan with sticky PR summary comment |
| [`codeql.yml`](../../.github/workflows/codeql.yml) | push/PR to `preview`, `canary`, `master` | CodeQL analysis for python and javascript |
| [`check-version.yml`](../../.github/workflows/check-version.yml) | PR to `master` | Fails if the PR did not bump the root `package.json` version |
| [`test-auto-state-duration.yml`](../../.github/workflows/test-auto-state-duration.yml) | push to `feat/time-tracking-spike`, `mrics/dev` (path-filtered) | Runs time-tracking + contributor-analytics pytest subset with hosted Postgres/Redis |
| [`test-github-app-configuration.yml`](../../.github/workflows/test-github-app-configuration.yml) | push to GitHub-integration branches (path-filtered) | Runs GitHub App configuration/sync contract pytest subset |
| [`build-frontend-image.yml`](../../.github/workflows/build-frontend-image.yml) | push to `mrics/dev` (path-filtered) + dispatch | Builds `ghcr.io/mrics-technologies/mrics-plane-frontend` (ARM64) |
| [`build-backend-image.yml`](../../.github/workflows/build-backend-image.yml) | push to `mrics/dev` (path-filtered) + dispatch | Builds `ghcr.io/mrics-technologies/mrics-plane-backend` (amd64+arm64) |
| [`build-branch.yml`](../../.github/workflows/build-branch.yml) | push to `preview`/`canary`, or manual dispatch (Build/Release) | Builds + pushes admin/web/space/live/api/proxy (+ optional AIO) Docker images to Docker Hub; publishes release assets and GitHub releases |
| [`feature-deployment.yml`](../../.github/workflows/feature-deployment.yml) | manual dispatch | Builds an AIO feature image to Docker Hub and deploys it to a Kubernetes feature-preview namespace via Helm (over Tailscale) |

## Environment configuration surface

- **Root-level**: [`turbo.json`](../../turbo.json) `globalEnv` lists the shared build-time environment variables (`VITE_API_BASE_URL`, `VITE_WEB_BASE_URL`, `VITE_ADMIN_BASE_*`, `VITE_SPACE_BASE_*`, `VITE_LIVE_BASE_*`, `SENTRY_*`, `LOG_LEVEL`, `NODE_ENV`, `APP_VERSION`, `DEV`).
- **API**: [`plane/settings/common.py`](../../apps/api/plane/settings/common.py) is the single source of truth for API env vars (`DATABASE_URL`/`POSTGRES_*`, `REDIS_URL`, `AMQP_URL`/`RABBITMQ_*`, `AWS_*`, `USE_MINIO`, `WEBHOOK_ALLOWED_IPS`/`WEBHOOK_ALLOWED_HOSTS`/`WEBHOOK_DISALLOWED_DOMAINS`, `SESSION_COOKIE_*`, `CORS_ALLOWED_ORIGINS`, `ENABLE_DRF_SPECTACULAR`, retention windows, etc.).
- **Live**: [`apps/live/src/env.ts`](../../apps/live/src/env.ts) validates its env with zod (`API_BASE_URL`, `LIVE_SERVER_SECRET_KEY`, `REDIS_*`, `CORS_ALLOWED_ORIGINS`, `LIVE_BASE_PATH`, compression options).
- **Frontends**: build-time `VITE_*` args in each app's Dockerfile (see [frontend.md](./frontend.md#application-composition)).
- **Proxy**: [`apps/proxy/Caddyfile.ce`](../../apps/proxy/Caddyfile.ce) reads `{$FILE_SIZE_LIMIT}`, `{$BUCKET_NAME}`, `{$CERT_EMAIL}`, `{$CERT_ACME_CA}`, `{$CERT_ACME_DNS}`, `{$TRUSTED_PROXIES}`, `{$SITE_ADDRESS}`; `docker-compose.yml` defaults `FILE_SIZE_LIMIT=5242880` and `BUCKET_NAME=uploads`.
- Secret values are never stored in this repository's documentation; env files are git-ignored (`.gitignore` ignores `.env*`).

## Troubleshooting navigation (no secrets required)

- **Setup failures** — follow [`CONTRIBUTING.md`](../../CONTRIBUTING.md) prerequisites (Docker, Node 20+, Python 3.8+, Postgres 14+, Redis, 12 GB RAM) and rerun `./setup.sh`.
- **Local stack issues** — check service health with `docker compose -f docker-compose-local.yml ps`; the API entrypoint runs `wait_for_db`/`wait_for_migrations` before starting.
- **API test stack issues** — see the troubleshooting section of [`apps/api/tests/RUNNING_TESTS.md`](../../apps/api/tests/RUNNING_TESTS.md) (missing `.env`, stale images, MinIO bucket, teardown with `-v`).
- **Deployment/CI** — the workflows above are declarative; for live-incident handling refer to the GitHub integration operations doc where relevant ([../github-integration/operations-and-troubleshooting.md](../github-integration/operations-and-troubleshooting.md)). General production operations are outside this repository's scope.

## Where to look next

- [Testing and contributing](./testing-and-contributing.md) — setup, checks, and API tests.
- [Applications](./applications.md) — per-app runtime/serving details.
- [Backend (API)](./backend.md) — settings topology and runtime entry scripts.
