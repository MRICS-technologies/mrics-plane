# MRICS Plane — Deploying with Coolify (Qualify)

This is the **primary deployment method**. The stack is deployed as a Coolify
**Docker Compose resource** — no manual docker commands, no server builds.
Multi-arch images are pulled from GHCR automatically (amd64 or arm64, whatever
the Coolify server runs).

Total time on a fresh Coolify project: **~5 minutes**.

---

## Prerequisites (one-time, per Coolify instance)

1. **GHCR registry access** (images are private until you make them public):
   Coolify → **Keys & Tokens → Docker Registries** → add `ghcr.io` with a
   GitHub username + PAT that has `read:packages`. Without this, pulls fail
   with `unauthorized`.
2. A Coolify **server with the proxy running** (Traefik). Note its network
   name — default is `coolify` (already the default of `PLANE_PROXY_NETWORK`).
3. DNS: create an A/AAAA record for your Plane domain → Coolify server IP.

## Deploy (step by step)

1. **Create the resource**
   Coolify → Project → Environment → **+ New Resource → Docker Compose (Empty)**.

2. **Paste the compose**
   Copy the contents of [`deployments/docker/docker-compose.yml`](../docker/docker-compose.yml)
   into the compose editor. Name the resource (e.g. `plane`).

3. **Set environment variables**
   Open the resource → **Environment** (bulk edit) and paste:

   ```env
   PLANE_PUBLIC_DOMAIN=plane.example.com
   WEB_URL=https://plane.example.com
   SECRET_KEY=<openssl rand -hex 32>
   POSTGRES_PASSWORD=<openssl rand -hex 16>
   RABBITMQ_PASSWORD=<openssl rand -hex 16>
   ADMIN_EMAIL=you@company.com
   ADMIN_PASSWORD=<strong password>
   LIVE_TOKEN=<openssl rand -hex 16>
   AWS_ACCESS_KEY_ID=<minio user>
   AWS_SECRET_ACCESS_KEY=<openssl rand -hex 24>
   ```

   Generate secrets anywhere: `openssl rand -hex 32`.
   All other variables have sane defaults (see [`.env.example`](../docker/.env.example)).

4. **Pin image tags (recommended for prod)**
   Default tags are `:dev` (rolling). For production pin the SHA tag built by CI:

   ```env
   PLANE_BACKEND_IMAGE=ghcr.io/mrics-technologies/mrics-plane-backend:dev-<sha7>
   PLANE_FRONTEND_IMAGE=ghcr.io/mrics-technologies/mrics-plane-frontend:dev-<sha7>
   PLANE_ADMIN_IMAGE=ghcr.io/mrics-technologies/mrics-plane-admin:dev-<sha7>
   ```

5. **Deploy** → watch the deployment log. Plane-migrator runs migrations first,
   then the API boots (first boot ≈ 1–2 min: static collection + gunicorn).

6. **Verify**
   - `https://<domain>/` → Plane login page (200)
   - `https://<domain>/god-mode` → admin panel login (200, no redirect loop, no `:3000`)
   - `https://<domain>/api/instances/` → JSON config (200)
   - All sub-apps green in Coolify (db/redis/mq/minio healthy)

7. **Log into `/god-mode/`** with `ADMIN_EMAIL` / `ADMIN_PASSWORD` to finish
   instance setup, then invite users.

---

## Redeploy / upgrade

1. Merge code → CI builds new multi-arch `:dev-<sha7>` + `:dev` tags.
2. In Coolify:
   - Pinned tags: **Environment** → bump the `<sha7>` in the three
     `PLANE_*_IMAGE` vars → **Redeploy**.
   - Rolling `:dev`: **Redeploy** (pulls latest) — or use *Restart with
     pull-latest* if available on your Coolify version.
3. Migrations run automatically via plane-migrator before the new API starts.
   Expect 30–60 s of transient 502/503 during API restart — normal.

## Backup / restore (via Coolify or SSH)

```bash
# DB dump (run on the Coolify server; container names carry the stack suffix)
docker exec plane-db pg_dump -U plane plane | gzip > plane-$(date +%F).sql.gz

# Restore into a fresh stack: gunzip | docker exec -i plane-db \
#   psql -U plane -d plane   (then restart plane-api)
```
MinIO file volume can be mirrored with an alpine sidecar copy (see
docker README → Backup).

## Coolify-specific rules (learned in production — respect them)

| Rule | Why |
|---|---|
| **One Plane stack per proxy router names** | Router names (`plane-web`, `plane-api`, …) are global per Traefik. Deploying a **second** Plane stack (e.g. dev + prod) behind the same proxy requires search-replacing router/service names (e.g. `planedev-`). Traefik logs `router defined multiple times` otherwise. |
| **Keep `/god-mode` rule WITHOUT trailing slash** | `/god-mode/` only matches the slashed form; the bare URL then falls into plane-web → users see `/?next_path=/god-mode`. The compose in this repo is already correct. |
| **Don't strip the admin nginx redirect fix** | The image emits relative redirects (`/god-mode/`), never `host:3000`. If you build custom admin images, keep `absolute_redirect off`. |
| **GHCR auth is per-Coolify-instance** | `unauthorized` pull errors = registry token missing/expired, not a compose problem. |
| **Multi-arch tags are mandatory** | Coolify servers may be amd64 or arm64. Use `:dev*` multi-arch manifests (CI publishes them); per-arch `:dev-amd64-*` / `:dev-arm64-*` tags exist for pinning specific hosts. |

## Troubleshooting quick table

| Symptom | Fix |
|---|---|
| Pull `unauthorized` | Add/refresh GHCR registry token (Prereq 1) |
| 503 `no available server` | Router-name collision (rule 1) or service crashed: check sub-app logs |
| `/god-mode` bounces to `/?next_path=…` | Trailing slash crept into the rule (rule 2) |
| Redirect to `:3000` | Custom admin image missing nginx fix (rule 3) |
| API 502 right after deploy | Migrator/boot still running — wait 1–2 min |
| Signup/login email issues | Configure SMTP via `/god-mode/` → Settings → Email |
