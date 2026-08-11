# GitHub Integration

The MRICS Plane fork includes a native GitHub App integration for connecting a Plane instance to GitHub repositories, mapping repositories to Plane projects, creating branches from work items, and linking GitHub pull requests back to the right Plane issue.

## Status

| Capability                                         | Status                                                  |
| -------------------------------------------------- | ------------------------------------------------------- |
| Instance GitHub App configuration                  | Available                                               |
| Workspace installation and repository registration | Available                                               |
| Repository → Plane project mapping                 | Available                                               |
| Create or link a branch from a Plane issue         | Available                                               |
| Shared branch across multiple issues               | Available                                               |
| Signed `pull_request` webhook → Plane PR links     | Available; shared branches fan out to all linked issues |
| PR action → Plane workflow-state automation        | Not implemented                                         |

The current implementation is merged in `mrics/dev` and staged as `mrics-v1.4.2.5` on `https://plane-staging.scalezy.com`. Production promotion remains a separate backup + approval step.

## Documentation map

- [Administrator setup](./admin-setup.md) — configure the instance GitHub App, workspace installation, repositories, and mappings.
- [Pull request linking](./pull-request-linking.md) — what GitHub events do, how issues are resolved, and expected link behavior.
- [Operations and troubleshooting](./operations-and-troubleshooting.md) — live smoke test, diagnostics, incident handling, and rollback.
- [Developer guide](./developer-guide.md) — API surface, data model, test command, and code map.

## Roles

| Role            | Responsibility                                                                                           |
| --------------- | -------------------------------------------------------------------------------------------------------- |
| Instance admin  | Configures the GitHub App credentials and public webhook base URL in Plane’s instance/God-mode settings. |
| Workspace admin | Registers the GitHub installation and enables repositories available to the workspace.                   |
| Project admin   | Maps an enabled repository to the appropriate Plane project.                                             |
| Developer       | Uses the issue key in branch names or PR titles and verifies links on the Plane issue.                   |

## Security model

GitHub credentials remain server-side and write-only. The webhook endpoint is public only so GitHub can call it; it validates every side effect against the GitHub signature, active installation, enabled repository, and Plane mapping. Never store keys or webhook secrets in Git, docs, logs, tickets, or chat.

## Quick start

1. Complete [Administrator setup](./admin-setup.md).
2. Create or open a Plane issue in a mapped project, such as `TP-123`.
3. Use the GitHub panel to create a suggested branch such as `feature/muhammed-tp-123-fix-login`, or type an existing branch name to link it.
4. If one branch covers multiple issues, link the same branch from each relevant issue.
5. Open a PR from the linked branch. The PR appears on every issue linked to that branch.
6. Follow the [dev acceptance smoke test](./operations-and-troubleshooting.md#dev-acceptance-smoke-test).
