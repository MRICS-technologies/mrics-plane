# MRICS Plane — Coolify Staging & Production Promotion Workflow

This is the canonical Scalezy/MRICS Plane feature workflow.

**Rule zero:** all deploys happen through **Coolify (Qualify)**. Do not make
server-side image builds, hidden SSH patches, or ad-hoc Docker edits part of the
normal release path. If an emergency server fix is required, convert it into a
repo change before considering the release complete.

---

## Environment model

| Environment | Purpose | Data source | Deployment authority |
|---|---|---|---|
| Local | development + targeted tests | local/dev fixtures only | developer/agent machine |
| PR / CI | review, tests, image builds | none | GitHub Actions |
| Coolify staging | production-like validation | **fresh point-in-time clone of production DB + MinIO** | Coolify |
| Coolify production | live users | live DB + MinIO | Coolify |

Staging should be production-like, not production-connected. It must have its own
Postgres volume, MinIO volume/bucket, Redis, RabbitMQ, domain, secrets, and
external integration credentials.

---

## Agreed defaults

These decisions are intentionally explicit so future feature work does not re-open
the same questions.

| Question | Default |
|---|---|
| Reset staging from production every feature release? | **Yes** — before every production candidate. |
| Keep staging always online? | **Yes** — e.g. `plane-staging.scalezy.com`. |
| Staging email behavior | Use a test inbox/sink only. Never email real users from staging. |
| GitHub App for staging | Use a **separate staging GitHub App**. |
| GitHub repos for staging | Use **test repos by default**. Real-repo testing is allowed only as an explicit, controlled final acceptance test. |
| Production approval | Hijazi approves after staging testing. |
| Production image tags | Use pinned SHA/digest tags, not rolling `:dev`. |
| Pre-production backup | Mandatory fresh backup before every production deploy. |
| Staging user data | Full prod clone is acceptable while this is internal Scalezy Plane; revisit anonymization if external/customer users grow. |
| Production downtime target | Under ~2 minutes; short 502/503 during API/migrator restart is expected. |
| Incomplete features | Use feature flags. Do not expose half-built features in production. |
| Manual DB edits | Emergency only; normal changes are migrations, seeds, or admin UI actions. |

### Controlled real-repo GitHub testing

Staging normally uses test repositories. If a feature needs real-world GitHub
behavior before production, do a controlled acceptance test:

1. Pick one approved real repository.
2. Pick one approved test issue/project.
3. Use clearly named branches, e.g. `staging/hijazi-test-<date>`.
4. Disable mass/bulk actions.
5. Verify webhook side effects in logs.
6. Clean up branches/comments/test PRs after acceptance.

Production and staging must not both act as write-capable automation against the
same real repository unless that test is explicitly approved.

---

## Feature release flow

### 1. Local development

1. Branch from current `origin/mrics/dev`.
2. Implement feature behind a flag if it is not guaranteed complete.
3. Add/modify migrations only through normal Django migration flow.
4. Run targeted local checks:
   - backend unit/API tests for touched areas
   - frontend/admin typecheck or targeted build for touched apps
   - migration sanity: `migrate --check` and `makemigrations --check --dry-run`
   - lint/format for changed files
5. Open PR to `mrics/dev`.

### 2. PR and CI

1. CI must pass.
2. Review must approve.
3. Merge with a merge commit.
4. GitHub Actions builds immutable, multi-arch images:
   - backend
   - frontend
   - admin
   - `linux/amd64` + `linux/arm64`
5. Record the candidate SHA/tag, e.g. `dev-<sha7>`.

### 3. Prepare Coolify staging

Staging is validated against a fresh clone of production, not old/stale staging
data.

1. Confirm staging Coolify service exists with its own volumes and domain.
2. Disable side effects:
   - email → test sink
   - GitHub App → staging app
   - webhooks/callback URLs → staging domain
   - scheduled jobs that can mutate external systems → disabled or sandboxed
3. Clone production data into staging:
   - `pg_dump` production Postgres → restore into staging Postgres
   - mirror production MinIO objects → staging MinIO
   - do **not** share prod DB/MinIO/Redis/RabbitMQ writable storage
4. Point staging images to the candidate SHA/tag.
5. Deploy from the Coolify UI.
6. Wait for `plane-migrator` to exit `0` and API to boot.

### 4. Staging proof gates

A staging URL returning 200 is not enough. Before production approval, verify:

- **Data parity before migration:** users/workspaces/projects/issues/key tables
  match production snapshot counts.
- **Migration gate:** candidate migrator exits `0`; then run:
  - `python manage.py migrate --check`
  - `python manage.py makemigrations --check --dry-run`
- **Routes:**
  - `/` → 200
  - `/api/instances/` → 200 JSON
  - `/god-mode` and `/god-mode/` → admin SPA; no `/?next_path` loop; no `:3000`
  - `/spaces/` → 200
  - auth routes route to API, not web fallback
- **Feature checks:** custom GitHub/worklog routes return expected 200/401/405;
  background jobs and webhook handlers do not error.
- **User/product acceptance:** Hijazi tests staging and explicitly approves prod.

### 5. Production promotion

Production receives the same code/image candidate proven in staging. We do not
copy staging DB into production.

1. Announce deploy window if needed.
2. Take fresh production backups:
   - Postgres dump
   - MinIO/object snapshot or mirror
   - current Coolify compose/env snapshot
3. Update production Coolify image refs to the exact candidate SHA/digest.
4. Deploy through Coolify.
5. Expect a short 502/503 while migrator/API restart.
6. Verify production:
   - routes listed above
   - key data counts
   - logs clean
   - custom feature smoke test
7. Keep rollback artifacts until Hijazi confirms the release is stable.

---

## Rollback model

Rollback must be prepared before production mutation.

- Before migrations: revert Coolify image refs to the previous pinned tags and redeploy.
- After migrations: old images may not be schema-compatible. Real rollback means
  restoring the pre-deploy Postgres + MinIO snapshots and previous image refs.
- If a migration has no safe reverse path, treat snapshot restore as the rollback.

---

## Required report format per release

Every release candidate should end with a short report:

```text
Candidate: <merge sha / image tags>
Staging service: <Coolify resource + URL>
Staging data snapshot: <source prod backup timestamp>
Migration gate: PASS/FAIL
Feature checks: PASS/FAIL
Known risks: ...
User acceptance: approved by <name/date> or pending
Production backup: <timestamp/path/checksum summary>
Production deploy: pending/done
Rollback artifact: <compose snapshot + DB/object backup>
```

---

## Anti-patterns

Do not do these as normal workflow:

- Build frontend/admin images on the Coolify server.
- Patch containers manually and leave the fix outside the repo.
- Use staging as a long-lived independent database for migration proof.
- Copy staging DB into production.
- Test staging against real GitHub repos without explicit approval.
- Deploy production from rolling tags without recording the exact SHA/digest.
- Cut over production when `makemigrations --check --dry-run` reports drift.
