# Usage — branches, links, and PRs

## Create a branch from an issue

1. Open the issue (full screen) → the **GitHub panel**
2. Click **Create branch** — the input is pre-filled with a suggested name:
   `feature/<ISSUE-ID>-<slug>` (e.g. `feature/ALLDEV-51-fix-login`)
3. Confirm → the branch is created on GitHub off the project's default base
   branch, and the issue is linked to it

- Branch names are unique per issue (the issue ID is part of the name), so
  recreating a branch is safe — the existing link is reused, never duplicated
- Creating a branch **requires** a mapped repository on the project; without
  one, the button is hidden

## Link an issue to an existing branch

You don't have to create a branch — if the work already lives in a branch:

1. Open the issue → GitHub panel → **Create branch**
2. **Delete the suggested name** and type the existing branch name (e.g.
   `hotfix/payments`)
3. Confirm → the issue is **linked** to the existing branch. No new branch is
   created — the endpoint checks GitHub first and links when it exists

The linked branch shows in the issue's GitHub panel with its ref and URL.

## Pull-request linking (automatic)

When a PR is opened on GitHub from a branch linked to an issue (or a branch
whose name contains the issue ID), the webhook **links the PR to the issue
automatically**:

- Correlation is by **branch name** (the primary, deterministic signal) with
  fallback to the PR title
- The PR appears in the issue's GitHub panel with its state
  (`open` / `merged` / `closed`)
- Link state updates are idempotent and timestamp-safe — stale webhook events
  never regress a newer state

## The issue GitHub panel

| Element                  | Behavior                                      |
| ------------------------ | --------------------------------------------- |
| **Create / link branch** | Creates or links a branch (see above)         |
| **Linked branches**      | Branch name, URL, and the issue it belongs to |
| **Linked PRs**           | PR number, state, and URL                     |

> 💡 **Phase 2 (planned):** issue state transitions driven by PR events —
> `ready_for_review` moves the issue to In Review, merge moves it to Done,
> requested changes moves it back to Started. The linking itself (this page)
> already works end to end.

## Multiple repos per project

When a project has several mapped repositories:

- The issue panel shows a **repository selector** before creating a branch
- The **default mapping** is pre-selected

## Time tracking (the other MRICS feature)

The fork also ships **work-log / time tracking**: issues carry a timer and
state-duration tracking (wall-clock time spent in each state), shown as
`Xh Ym` (or `Xd Zh` for 24+ hours). Duration display uses 24-hour calendar
days — state duration is wall-clock time, not effort.
