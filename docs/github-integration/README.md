# GitHub Integration

The MRICS Plane fork includes a native GitHub App integration for connecting a Plane instance to GitHub repositories, mapping repositories to Plane projects, creating branches from work items, and linking GitHub pull requests back to the right Plane issue.

## Status

| Capability | Status |
| --- | --- |
| Instance GitHub App configuration | Available |
| Workspace installation and repository registration | Available |
| Repository → Plane project mapping | Available |
| Create a branch from a Plane issue | Available |
| Signed `pull_request` webhook → Plane PR link | Deployed to dev; final live GitHub-delivery smoke test pending |
| PR action → Plane workflow-state automation | Not implemented |

The current implementation is merged in `mrics/dev`. It passed the hosted PostgreSQL/Redis contract suite on the merged SHA and is deployed to the MRICS dev instance. Production is not part of this rollout.

## Documentation map

- [Administrator setup](./admin-setup.md) — configure the instance GitHub App, workspace installation, repositories, and mappings.
- [Pull request linking](./pull-request-linking.md) — what GitHub events do, how issues are resolved, and expected link behavior.
- [Operations and troubleshooting](./operations-and-troubleshooting.md) — live smoke test, diagnostics, incident handling, and rollback.
- [Developer guide](./developer-guide.md) — API surface, data model, test command, and code map.

## Roles

| Role | Responsibility |
| --- | --- |
| Instance admin | Configures the GitHub App credentials and public webhook base URL in Plane’s instance/God-mode settings. |
| Workspace admin | Registers the GitHub installation and enables repositories available to the workspace. |
| Project admin | Maps an enabled repository to the appropriate Plane project. |
| Developer | Uses the issue key in branch names or PR titles and verifies links on the Plane issue. |

## Security model

GitHub credentials remain server-side and write-only. The webhook endpoint is public only so GitHub can call it; it validates every side effect against the GitHub signature, active installation, enabled repository, and Plane mapping. Never store keys or webhook secrets in Git, docs, logs, tickets, or chat.

## Quick start

1. Complete [Administrator setup](./admin-setup.md).
2. Create a Plane issue in a mapped project, such as `TP-123`.
3. Create a PR from the enabled repository with `TP-123` in its branch name or title.
4. Follow the [dev acceptance smoke test](./operations-and-troubleshooting.md#dev-acceptance-smoke-test).
