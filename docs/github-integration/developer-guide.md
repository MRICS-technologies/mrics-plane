# Developer guide

This page is for maintainers extending or reviewing the GitHub integration.

## API surface

| Resource                                  | Route                                                                                            |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Public GitHub webhook                     | `POST /api/github/webhook/`                                                                      |
| Instance GitHub App configuration         | `/api/instances/github-app/`                                                                     |
| Workspace installation                    | `/api/workspaces/<workspace-slug>/github/installation/`                                          |
| Workspace repositories                    | `/api/workspaces/<workspace-slug>/github/repositories/`                                          |
| Project repository mappings (list/attach) | `/api/workspaces/<workspace-slug>/projects/<project-id>/github/mappings/`                        |
| Set default / remove a mapping            | `PATCH {"is_default": true}` / `DELETE` on `.../github/mappings/<mapping-id>/`                   |
| Issue Git links                           | `/api/workspaces/<workspace-slug>/projects/<project-id>/issues/<issue-id>/git-links/`            |
| Create issue branch                       | `/api/workspaces/<workspace-slug>/projects/<project-id>/issues/<issue-id>/github/create-branch/` |
| Workspace teams (list/create)             | `/api/workspaces/<workspace-slug>/teams/`                                                        |
| Rename / delete a team                    | `PATCH` / `DELETE` on `/api/workspaces/<workspace-slug>/teams/<team-id>/`                        |
| Add team members (moves from other teams) | `POST {"member_ids": [...]}` on `/api/workspaces/<workspace-slug>/teams/<team-id>/members/`      |
| Remove a team member                      | `DELETE /api/workspaces/<workspace-slug>/teams/<team-id>/members/<user-id>/`                     |
| Team repositories of a project            | `GET .../projects/<project-id>/github/team-repositories/`                                        |
| Set / clear a team's project repository   | `PUT {"mapping_id": "<mapping-id>" \| null}` on `.../github/team-repositories/<team-id>/`        |

The webhook route deliberately has no browser/session authentication; authorization comes from signature validation and the stored GitHub/Plane relationships.
It opts out of DRF's automatic throttling and throttles in `post()` after the signature check: signed deliveries on `GitHubWebhookThrottle` (`GITHUB_WEBHOOK_RATE_LIMIT`), everything else on the anon bucket (see [Webhook rate limit](operations-and-troubleshooting.md#webhook-rate-limit)).

## Data model

- `GithubAppInstallation` represents an active GitHub App installation for a Plane workspace.
- `GithubEnabledRepository` constrains which installation repositories are usable.
- `RepoProjectMapping` authorizes a repository to affect a specific Plane project.
- `IssueGitLink` stores branch and PR links. PR rows include the PR number and GitHub update timestamp.
- `TeamMember` (hard-deleted rows, one live team per workspace member) and `ProjectTeamRepository` (per project and team, the `RepoProjectMapping` its branches go to; one live row per project and team) drive the branch repository preference; the rule lives in `apps/api/plane/services/github/team_repo.py`.
- `GithubWebhookDelivery` stores only a delivery ID and event name for deduplication. It must never store raw payloads or secrets.

### Team repositories per project

- `GET .../github/team-repositories/` (project admins and members) returns every live team of the workspace, by name: `[{"team": {"id", "name", "member_count"}, "mapping_id": "<uuid>" | null}]`. `member_count` counts active workspace members only.
- `PUT .../github/team-repositories/<team-id>/` (project admins) with `{"mapping_id": "<uuid>"}` sets the team's repository, `null` clears it; it returns the same row shape. `400` when `mapping_id` is not a live mapping of this project, `404` for a team that is not live in this workspace.
- Branch creation without `repo`: the requesting user's team row for this project, else the project default. The mapping list adds `default_for_teams` and `is_my_team_default` per mapping, for this project only.
- Rows are hard-deleted by the `PUT` with `null`, and in the same transaction as mapping removal (`RepoProjectMappingViewSet.destroy`), team delete and `soft_delete_installations` (force disconnect, App ID reset). Deleting a whole project or workspace soft-deletes them through the usual cascade; reads ignore soft-deleted rows. The `PUT` locks the project, team and mapping rows so it cannot land on a row being removed.
- The resolver and the mapping-list hints skip rows whose mapping or team is soft-deleted, or whose mapping's repository is disabled, soft-deleted, or on a soft-deleted or inactive installation; legacy mappings without a repository row stay usable. `GET .../team-repositories/` still returns those rows, so admins see the saved choice.

## Code map

| Concern                           | Location                                                    |
| --------------------------------- | ----------------------------------------------------------- |
| Route definitions                 | `apps/api/plane/app/urls/github_sync.py`                    |
| Webhook validation and processing | `apps/api/plane/app/views/github_sync.py`                   |
| Link and mapping models           | `apps/api/plane/db/models/integration/github_sync.py`       |
| Instance GitHub App routes        | `apps/api/plane/license/urls.py`                            |
| Contract tests                    | `apps/api/plane/tests/contract/api/test_github_sync.py`     |
| Team repository per project       | `apps/api/plane/services/github/team_repo.py`               |
| Team endpoints                    | `apps/api/plane/app/views/workspace/team.py`                |
| Team contract tests               | `apps/api/plane/tests/contract/api/test_workspace_teams.py` |
| Hosted test workflow              | `.github/workflows/test-github-app-configuration.yml`       |

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
plane/tests/contract/api/test_github_setup_flow.py
plane/tests/contract/api/test_workspace_teams.py
```

## Change rules

- Preserve raw-body HMAC verification and constant-time comparison.
- Treat missing/unrecognized webhook input as non-side-effecting.
- Keep webhook bodies, signatures, private keys, client secrets, and webhook secrets out of logs and test fixtures.
- Keep PR identity workspace-scoped and retain transaction boundaries around delivery dedupe/upserts.
- Extend contract coverage for every new event action or correlation strategy.
- Do not combine PR-linking changes with workflow-state automation without a separate design, review, and acceptance plan.
