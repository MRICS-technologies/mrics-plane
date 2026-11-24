# Operations and troubleshooting

Use this guide to accept the dev rollout, investigate a failed delivery, or stop webhook effects safely.

## Dev acceptance smoke test

Run this against the dev instance before any production discussion.

1. Confirm the GitHub App configuration, active installation, enabled repository, and project mapping are present.
2. Create or choose one or more Plane issues in the mapped project, for example `TP-123` and optionally `TP-124`.
3. Use the GitHub panel to create or link a branch. For a shared-branch test, link the same branch from both issues.
4. Open a PR in the enabled repository using the linked branch or a key in the title:

   ```text
   TP-123 test webhook linking
   ```

5. In GitHub App settings, open the webhook delivery and confirm it succeeded.
6. In Plane, open every issue linked to that branch and confirm the PR link appears on each one.
7. Push another commit and confirm the same link rows remain open and are updated.
8. Close/reopen or merge the PR and confirm the linked issues reflect the new PR state.
9. Re-deliver the same GitHub delivery from GitHub’s UI and confirm Plane does not create duplicate links.

Record the result without copying request bodies, signatures, secrets, cookies, or access tokens.

## Health checks

Verify public routing and API authentication separately:

```bash
curl -fsS -o /dev/null -w '%{http_code}
' <PLANE_PUBLIC_URL>/
curl -fsS -o /dev/null -w '%{http_code}
' <PLANE_PUBLIC_URL>/api/v1/users/me/
```

The root should return `200`. The second endpoint should return `401` when no user credentials are supplied; that proves the API is reachable and enforcing authentication.

## Delivery outcomes

| Observation                     | Meaning                                                                                                        | First action                                                                                                      |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `401 Invalid signature`         | GitHub and Plane do not share the same webhook secret, or the request was altered before it reached Plane.     | Re-enter the same secret directly in both admin UIs; check reverse-proxy handling of request bodies.              |
| `413`                           | Payload exceeds the 1 MiB webhook limit.                                                                       | Do not raise the limit casually; inspect the event and confirm the endpoint receives only intended PR deliveries. |
| `429`                           | The webhook rate limit for this client IP was hit; the delivery was not processed.                             | Redeliver it from GitHub, then see [Webhook rate limit](#webhook-rate-limit).                                     |
| `200` but no link               | The delivery may be duplicated, unsupported, disabled, unmapped, ambiguous, or not tied to a resolvable issue. | Check the installation, repository state, project mapping, branch link, and issue key.                            |
| Duplicate links                 | Unexpected; replay protection and PR uniqueness should prevent this.                                           | Disable the repository mapping, preserve non-secret metadata, and investigate before re-enabling.                 |
| Link appears on the wrong issue | Treat as a correlation defect.                                                                                 | Disable the mapping and preserve PR number, delivery ID, project identifiers, and timestamps only.                |

## Webhook rate limit

Deliveries with a valid signature are limited per client IP by `GITHUB_WEBHOOK_RATE_LIMIT` (default `600/minute`). Requests with a missing or invalid signature, or any request while the GitHub App is not configured, stay on the shared anonymous limit (`30/minute` per IP) and never use the webhook budget. A `413` is returned before either limit is counted. Both limits are counted after the signature check, so junk traffic from the same IP cannot crowd out real deliveries; the trade-off is that every unsigned request costs one configuration read and an HMAC over at most 1 MiB before it is counted.

GitHub does not retry failed deliveries. A `429` shows the delivery as failed in the GitHub App's **Advanced → Recent deliveries**, and the PR update is missing in Plane until you redeliver it from there; the API logs `signed delivery throttled` when this happens. If it does, raise `GITHUB_WEBHOOK_RATE_LIMIT` (`<count>/<second|minute|hour|day>`; an invalid value logs a warning and falls back to `600/minute`) and check that `NUM_PROXIES` matches the number of proxies in front of the API, so the limit is keyed on GitHub's address rather than the proxy's or a client-supplied header.

Raise the per-minute count rather than using a huge count over a long window: DRF stores one timestamp per counted request in the cache entry, so a value like `50000/hour` makes every delivery read and write a list of up to 50,000 timestamps.

On the Coolify stack (`deployments/docker/docker-compose.yml`), the variable is passed to the API through the compose `backend-env` block; the default works without any configuration.

## Safe pause and rollback

To stop **new** webhook effects without deleting history:

1. Disable the repository in the Plane workspace, or remove the project mapping.
2. If necessary, disable the GitHub App webhook or uninstall the app from the repository.
3. Preserve existing Plane links for investigation; do not cascade-delete records as a first response.

No production rollback is described here because production deployment is not approved for this feature.

## Deployment discipline

A successful image build does not prove the running service pulled it. For a dev rollout:

1. Build matching backend and frontend images for the target commit.
2. Restart the Coolify service with a forced latest-image pull.
3. Wait for the service start sequence.
4. Probe the public frontend and protected API.
5. Run the real GitHub delivery smoke test.

If Coolify reports an aggregate health warning while public probes are good, investigate the specific container health check before declaring the feature accepted.

### Migration 0132 was replaced (team repositories)

`0132_team_member_team_default_repository` (from PR #44, never released to production) was replaced by `0132_team_member_project_team_repository`. A database that applied the old 0132 (a dev database, or any environment deployed from `mrics/dev` that is not re-cloned from production) must undo it before the new code migrates; otherwise `migrate` fails with `relation "team_members" already exists`. Either:

- before switching, on the old code: `python manage.py migrate db 0131`; or
- after switching (this loses team memberships):

  ```sql
  BEGIN;
  DROP TABLE team_members;
  ALTER TABLE teams DROP COLUMN default_repository_id;
  DELETE FROM django_migrations WHERE app = 'db' AND name = '0132_team_member_team_default_repository';
  COMMIT;
  ```

then run `python manage.py migrate`. Production (at 0131) and staging (re-cloned from production) need nothing.
