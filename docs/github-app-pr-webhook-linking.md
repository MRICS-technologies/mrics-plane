# GitHub App Pull Request Webhook Linking

This document is the operator and maintainer guide for the MRICS Plane fork’s dynamic GitHub App integration and signed GitHub pull-request linking.

> **Scope:** This is fork-specific documentation. It describes the GitHub App setup, workspace/repository mapping, and the inbound `pull_request` webhook that creates or updates links on Plane issues. It does **not** automate Plane issue state transitions from PR activity.

## Current delivery status

- Merged into `mrics/dev` through [PR #3](https://github.com/MRICS-technologies/mrics-plane/pull/3), merge commit `67803a8d069bdaac269f098b76846d25367e54ac`.
- The merged SHA passed the hosted PostgreSQL/Redis contract suite: [GitHub Actions run 30616470428](https://github.com/MRICS-technologies/mrics-plane/actions/runs/30616470428).
- Matching backend and frontend images were built and deployed to the dev service. Public availability was verified on 2026-07-31 (`/` → `200`; protected `/api/v1/users/me/` → expected `401`).
- **Remaining acceptance:** one real GitHub App delivery against an enabled, mapped dev repository.

No production environment is included in this rollout.

## Architecture

```text
GitHub App pull_request event
  → POST /api/github/webhook/
  → raw-body HMAC verification
  → installation and enabled-repository validation
  → delivery replay/deduplication
  → mapped Plane issue resolution
  → IssueGitLink create/update
```

The setup has three distinct administration layers:

1. **Instance admin:** configures the GitHub App credentials in Plane’s instance/God-mode GitHub App configuration.
2. **Workspace admin:** registers the installation and enabled repositories for the workspace.
3. **Project admin:** maps an enabled repository to a Plane project.

This separation keeps GitHub credentials server-side and constrains webhook effects to an authorized workspace and mapped repository.

## Security contract

The endpoint is intentionally public to GitHub but accepts side effects only after validation.

- The webhook verifies `X-Hub-Signature-256` against the **raw request body** before processing JSON.
- Invalid signatures fail closed; malformed events do not create links.
- Webhook bodies and signatures are excluded from application request logging.
- Payloads are size-limited.
- `X-GitHub-Delivery` is required before side-effecting processing, providing replay/idempotency protection.
- Delivery records are handled transactionally.
- Pull-request identity is scoped to the Plane workspace/repository; stale event ordering cannot overwrite newer link state.
- Link restoration is soft-delete safe.

> [!warning]
> Never commit, log, document, or paste a GitHub App private key, client secret, or webhook secret. Enter secrets only through the intended GitHub and Plane administration UIs.

## GitHub App setup

### 1. Configure the instance GitHub App

An authenticated Plane instance admin configures the app in the GitHub App administration screen. The backend exposes this configuration under `/api/instances/github-app/`; secret fields are write-only.

Configure the GitHub App with the required credentials and a public webhook base URL. For the dev instance, the endpoint is:

```text
https://mrics-plane-dev.193.122.88.185.sslip.io/api/github/webhook/
```

For any other environment, use:

```text
<PLANE_PUBLIC_URL>/api/github/webhook/
```

The URL must be public HTTPS and must terminate at the Plane API service, not at a frontend-only route.

### 2. Subscribe to the right event

In GitHub App settings, enable the **Pull requests** webhook event. The endpoint processes `pull_request` lifecycle events including:

- `opened`
- `reopened`
- `synchronize`
- `closed`
- `merged`

### 3. Register the workspace installation and repositories

From the workspace GitHub settings:

1. Register the intended GitHub App installation.
2. Load the repositories accessible to that installation.
3. Enable the repository intended for the Plane project.
4. Map that repository to the Plane project.

Relevant API surfaces:

```text
/api/workspaces/<workspace-slug>/github/installation/
/api/workspaces/<workspace-slug>/github/repositories/
/api/workspaces/<workspace-slug>/projects/<project-id>/github/mappings/
```

A webhook for an inactive installation, disabled repository, or unmapped project must not create a Plane link.

## Dev acceptance smoke test

Run this only against the dev instance before considering production.

1. Create or choose a test Plane issue in the mapped project, for example `TP-123`.
2. Create a GitHub pull request in the enabled repository with the issue key in its title or branch, for example:

   ```text
   TP-123 test webhook linking
   ```

3. In GitHub App settings, inspect the webhook delivery. It should be successful.
4. In Plane, open `TP-123` and confirm the PR link appears with its URL and lifecycle state.
5. Update the PR, then close/reopen or merge it; confirm the same Plane link updates rather than duplicating.
6. Re-deliver the same GitHub delivery from GitHub’s UI and confirm no duplicate link is created.

### Expected outcomes

| Scenario | Expected Plane behavior |
| --- | --- |
| Valid mapped PR delivery | Creates or updates one issue PR link |
| Replayed delivery | No duplicate side effect |
| Invalid signature | Rejected before processing |
| Missing delivery ID | Acknowledged without side effects |
| Disabled repository or installation | No link is created/updated |
| PR with no resolvable mapped issue | No unrelated issue is linked |

## Automated validation

The focused contract workflow uses PostgreSQL 16 and Redis 7 and covers configuration, mappings, webhook handling, and logging protections.

```bash
gh workflow run test-github-app-configuration.yml \
  --repo MRICS-technologies/mrics-plane \
  --ref mrics/dev
```

The workflow file is `.github/workflows/test-github-app-configuration.yml`. It runs these focused suites:

```text
plane/tests/contract/api/test_github_app_configuration.py
plane/tests/contract/api/test_github_sync.py
plane/tests/contract/api/test_github_workspace_installation_models.py
plane/tests/contract/api/test_github_s2_mapping_api.py
```

## Operations and rollback

- **Do not deploy production** until the dev smoke test above passes and an explicit production-readiness review is approved.
- To stop new webhook effects, disable the workspace installation or repository mapping in Plane, or disable the GitHub App webhook in GitHub. Historical links remain visible.
- Treat signature failures, unexpected duplicate links, or cross-workspace link attempts as security incidents: disable the affected installation/repository first, preserve non-secret delivery metadata, and investigate before re-enabling.
- A Coolify restart without a latest-image pull can leave old images running. For a promoted image rollout, rebuild the matching backend/frontend images and restart the dev service with a forced pull, then probe the public frontend and protected API separately.

## Code map

| Concern | Primary location |
| --- | --- |
| Webhook routes | `apps/api/plane/app/urls/github_sync.py` |
| Webhook handling | `apps/api/plane/app/views/github_sync.py` |
| GitHub configuration routes | `apps/api/plane/license/urls.py` |
| Models and constraints | `apps/api/plane/db/models/integration/github_sync.py` |
| Contract tests | `apps/api/plane/tests/contract/api/test_github_sync.py` |
| Hosted contract workflow | `.github/workflows/test-github-app-configuration.yml` |
