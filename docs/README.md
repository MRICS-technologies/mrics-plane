# MRICS Plane — GitHub Integration

MRICS Plane is a fork of [Plane](https://plane.so) (open-source project management)
with two additions over upstream: **work-log / time tracking** and a **GitHub
integration** that links issues, branches, and pull requests.

This documentation covers the GitHub integration as shipped. It is maintained
with the code — every released round updates these pages.

## Contents

- [Getting started](github-integration/getting-started.md) — install the GitHub App, connect a workspace, enable repositories
- [Usage](github-integration/usage.md) — create or link branches, pull-request linking, the issue panel
- [Troubleshooting](github-integration/troubleshooting.md) — org access, webhook delivery, reconnects
- [Releases](github-integration/releases.md) — what shipped in each round

## Feature summary

| Capability                                                                                   | Status     |
| -------------------------------------------------------------------------------------------- | ---------- |
| One-click GitHub App creation (manifest flow, no credentials typed)                          | ✅         |
| Workspace-level installation (one per workspace, ownership-protected)                        | ✅         |
| Live repository discovery (no manual IDs)                                                    | ✅         |
| Repo → project mapping (multiple repos per project, one default; same repo in many projects) | ✅         |
| Create a branch per issue (issue-ID naming, idempotent)                                      | ✅         |
| Link an issue to an _existing_ branch manually                                               | ✅         |
| PR auto-linking by branch name (webhook)                                                     | ✅         |
| Issue state transitions on PR events (In Review / Done / Todo)                               | 🚧 Phase 2 |
| Multiple GitHub Apps per instance                                                            | 🚧 Phase 2 |

## Architecture in one picture

```
┌───────────────────────── INSTANCE ─────────────────────────┐
│  GitHub App (identity, created once via one-click manifest)│
└────────────────────────────────────────────────────────────┘
                          │
┌───────────────────────── WORKSPACE ────────────────────────┐
│  Installation (org + granted repos) — one per workspace    │
│  Enabled repositories (live from GitHub)                   │
└────────────────────────────────────────────────────────────┘
                          │
┌───────────────────────── PROJECT ──────────────────────────┐
│  Repo → project mappings (base branch + default flag)      │
└────────────────────────────────────────────────────────────┘
                          │
┌───────────────────────── ISSUE ─────────────────────────────┐
│  Create/link branch → PR → (Phase 2) state transitions     │
└────────────────────────────────────────────────────────────┘
```
