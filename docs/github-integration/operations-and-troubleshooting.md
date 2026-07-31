# Operations and troubleshooting

Use this guide to accept the dev rollout, investigate a failed delivery, or stop webhook effects safely.

## Dev acceptance smoke test

Run this against the dev instance before any production discussion.

1. Confirm the GitHub App configuration, active installation, enabled repository, and project mapping are present.
2. Create or choose a Plane issue in the mapped project, for example `TP-123`.
3. Open a PR in the enabled repository using a key in the title or branch:

   ```text
   TP-123 test webhook linking
   ```

4. In GitHub App settings, open the webhook delivery and confirm it succeeded.
5. In Plane, open `TP-123` and confirm exactly one PR link appears.
6. Push another commit and confirm the same link remains open and is updated.
7. Close/reopen or merge the PR and confirm the same link reflects the new state.
8. Re-deliver the same GitHub delivery from GitHub’s UI and confirm Plane does not create a duplicate link.

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

| Observation | Meaning | First action |
| --- | --- | --- |
| `401 Invalid signature` | GitHub and Plane do not share the same webhook secret, or the request was altered before it reached Plane. | Re-enter the same secret directly in both admin UIs; check reverse-proxy handling of request bodies. |
| `413` | Payload exceeds the 1 MiB webhook limit. | Do not raise the limit casually; inspect the event and confirm the endpoint receives only intended PR deliveries. |
| `200` but no link | The delivery may be duplicated, unsupported, disabled, unmapped, ambiguous, or not tied to a resolvable issue. | Check the installation, repository state, project mapping, branch link, and issue key. |
| Duplicate links | Unexpected; replay protection and PR uniqueness should prevent this. | Disable the repository mapping, preserve non-secret metadata, and investigate before re-enabling. |
| Link appears on the wrong issue | Treat as a correlation defect. | Disable the mapping and preserve PR number, delivery ID, project identifiers, and timestamps only. |

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
