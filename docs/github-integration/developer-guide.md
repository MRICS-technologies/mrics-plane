# Developer guide

This page is for maintainers extending or reviewing the GitHub integration.

## API surface

| Resource | Route |
| --- | --- |
| Public GitHub webhook | `POST /api/github/webhook/` |
| Instance GitHub App configuration | `/api/instances/github-app/` |
| Workspace installation | `/api/workspaces/<workspace-slug>/github/installation/` |
| Workspace repositories | `/api/workspaces/<workspace-slug>/github/repositories/` |
| Project repository mapping | `/api/workspaces/<workspace-slug>/projects/<project-id>/github/mappings/` |
| Issue Git links | `/api/workspaces/<workspace-slug>/projects/<project-id>/issues/<issue-id>/git-links/` |
| Create issue branch | `/api/workspaces/<workspace-slug>/projects/<project-id>/issues/<issue-id>/github/create-branch/` |

The webhook route deliberately has no browser/session authentication; authorization comes from signature validation and the stored GitHub/Plane relationships.

## Data model

- `GithubAppInstallation` represents an active GitHub App installation for a Plane workspace.
- `GithubEnabledRepository` constrains which installation repositories are usable.
- `RepoProjectMapping` authorizes a repository to affect a specific Plane project.
- `IssueGitLink` stores branch and PR links. PR rows include the PR number and GitHub update timestamp.
- `GithubWebhookDelivery` stores only a delivery ID and event name for deduplication. It must never store raw payloads or secrets.

## Code map

| Concern | Location |
| --- | --- |
| Route definitions | `apps/api/plane/app/urls/github_sync.py` |
| Webhook validation and processing | `apps/api/plane/app/views/github_sync.py` |
| Link and mapping models | `apps/api/plane/db/models/integration/github_sync.py` |
| Instance GitHub App routes | `apps/api/plane/license/urls.py` |
| Contract tests | `apps/api/plane/tests/contract/api/test_github_sync.py` |
| Hosted test workflow | `.github/workflows/test-github-app-configuration.yml` |

## Focused hosted test

The repository includes a reproducible PostgreSQL 16 + Redis 7 contract gate. Run it from GitHub Actions when the local environment does not provide those services:

```bash
gh workflow run test-github-app-configuration.yml \
  --repo MRICS-technologies/mrics-plane \
  --ref mrics/dev
```

The workflow executes:

```text
plane/tests/contract/api/test_github_app_configuration.py
plane/tests/contract/api/test_github_sync.py
plane/tests/contract/api/test_github_workspace_installation_models.py
plane/tests/contract/api/test_github_s2_mapping_api.py
```

## Change rules

- Preserve raw-body HMAC verification and constant-time comparison.
- Treat missing/unrecognized webhook input as non-side-effecting.
- Keep webhook bodies, signatures, private keys, client secrets, and webhook secrets out of logs and test fixtures.
- Keep PR identity workspace-scoped and retain transaction boundaries around delivery dedupe/upserts.
- Extend contract coverage for every new event action or correlation strategy.
- Do not combine PR-linking changes with workflow-state automation without a separate design, review, and acceptance plan.
