# MRICS Plane — Self-Hosted Deployment (Docker Compose)

Deploy the full MRICS Plane stack (web, admin/god-mode, API, workers, live, space,
PostgreSQL, Redis, RabbitMQ, MinIO) on **any server, any architecture** (amd64 / arm64),
behind an existing Traefik reverse proxy.

All images are pulled from GHCR as **multi-arch manifests** — Docker automatically
selects the right architecture for your host. No builds on the server.

## Prerequisites

- Docker Engine + Compose v2
- A Traefik instance already running (Coolify's proxy works as-is)
- A domain with an A/AAAA record pointing to the server

## Quickstart

```bash
git clone https://github.com/MRICS-technologies/mrics-plane.git
cd mrics-plane/deployments/docker

cp .env.example .env
# edit .env — set domain, secrets (openssl rand -hex 32), MinIO keys
$EDITOR .env

docker compose up -d
```

Then open `https://<your-domain>` and log into `/god-mode/` with
`ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env` to finish instance setup.

## What gets deployed

| Service | Purpose | Port (internal) |
|---|---|---|
| plane-web | Main SPA | 3000 |
| plane-admin | Admin panel (`/god-mode`) | 3000 |
| plane-space | Public site (`/spaces/`) | 3000 |
| plane-live | Realtime (`/live/`) | 3000 |
| plane-api | Django API (`/api/`, `/auth/`) | 8000 |
| plane-worker / beat-worker | Background jobs | — |
| plane-migrator | One-shot schema migrations (runs first) | — |
| plane-db / redis / mq / minio | Stateful backing services | — |

## Routing map (handled by Traefik labels — nothing to configure)

```
/                 -> plane-web    (priority 1, catch-all)
/api/ /auth/      -> plane-api    (priority 10)
/god-mode*        -> plane-admin  (priority 10, no trailing slash in rule!)
/spaces/          -> plane-space  (priority 10)
/live/            -> plane-live   (priority 10)
```

### Hardening notes baked into this stack

These fix real production bugs found during deployment — do not "simplify" them:

1. **`PathPrefix(`/god-mode`)` without trailing slash.** With a trailing slash,
   `/god-mode` (no slash) misses the rule, falls into plane-web, whose SPA bounces
   users to `/?next_path=/god-mode`. If you rename routes, keep both forms matching.
2. **`absolute_redirect off; port_in_redirect off;` in `apps/admin/nginx/nginx.conf`.**
   Without it, nginx 301s `/god-mode` → `http://host:3000/god-mode/`, leaking the
   internal port. Already in the repo image; kept correct here.
3. **Unique router names.** If you run more than one Plane stack behind the same
   Traefik (e.g. dev + prod), suffix every `traefik.http.routers.*` /
   `traefik.http.services.*` name per stack or Traefik will error with
   "router defined multiple times with different configurations".
4. **No Coolify `${SERVICE...}` placeholders here** — this compose is plain,
   portable Docker. Coolify users can paste it into a Docker Compose resource
   and set the same `.env` values in Coolify's env editor.

## Environment variables

See [.env.example](.env.example). Everything is configurable; only domain +
secrets are mandatory (`:?` guards fail fast with a clear message).

## Operations

```bash
docker compose logs -f plane-api         # tail API logs
docker compose run --rm plane-migrator   # re-run migrations
docker compose pull && docker compose up -d   # upgrade images
docker compose down                      # stop (data volumes preserved)
docker compose down -v                   # stop and DELETE ALL DATA
```

### Upgrades

Pin image tags for reproducibility (`:dev-<sha>`). To upgrade: change tag in
`.env`, then `docker compose pull && docker compose up -d`. The migrator runs
before the API starts, so schema upgrades are automatic.

### Backup

```bash
# Database
docker compose exec plane-db pg_dump -U plane plane | gzip > plane-$(date +%F).sql.gz
# Files
docker run --rm -v <project>_miniodata:/data -v $PWD:/backup alpine \
  tar czf /backup/minio-$(date +%F).tar.gz -C /data .
```

### Multi-stack on one Traefik (dev + prod)

Copy the directory, use a different `PLANE_PUBLIC_DOMAIN` and different container
names (`docker compose -p plane-dev`), and suffix router names per note 3 above.

## Architecture support

GHCR images are published as multi-arch manifests (`linux/amd64`, `linux/arm64`)
by CI (`.github/workflows/build-*-image.yml`). Deploying on ARM (e.g. Oracle
A1) or x86 requires no changes — Docker picks the matching manifest.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `/?next_path=/god-mode` loop | admin rule has trailing slash — remove it (note 1) |
| Redirect to `:3000` port | image built before the nginx fix — pull a newer tag (note 2) |
| "no available server" (503) | router name collision (note 3) or service down: `docker compose ps` |
| API 502 on first boot | migrator still running — wait ~1-2 min, then retry |
| GHCR pull unauthorized | private registry: `docker login ghcr.io` with a read:packages PAT |
