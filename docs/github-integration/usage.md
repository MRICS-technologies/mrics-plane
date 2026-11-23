# Usage — branches, links, and PRs

## Create a branch from an issue

1. Open the issue (full screen) → the **GitHub panel**
2. Click **Create / link branch** — the input is pre-filled with a suggested
   name that includes the current user's first name when available:
   `feature/<first-name>-<ISSUE-ID>-<slug>` (for example
   `feature/muhammed-alldev-51-fix-login`)
3. Confirm → the branch is created on GitHub off the project's default base
   branch, and the issue is linked to it

- The input is editable. If no usable first/display name is available, Plane
  falls back to the previous `feature/<ISSUE-ID>-<slug>` format.
- Recreating a branch link on the same issue is safe — the existing link is
  reused, never duplicated.
- A branch can intentionally be shared across multiple issues. Linking an
  already-linked branch to another issue creates a second issue link instead of
  treating the branch as claimed.
- Creating a branch **requires** a mapped repository on the project; without
  one, the button is hidden

## Link an issue to an existing branch

You don't have to create a branch — if the work already lives in a branch:

1. Open the issue → GitHub panel → **Create / link branch**
2. **Delete the suggested name** and type the existing branch name (e.g.
   `hotfix/payments`)
3. Confirm → the issue is **linked** to the existing branch. No new branch is
   created — the endpoint checks GitHub first and links when it exists

The linked branch shows in the issue's GitHub panel with its ref and URL. The
same branch can appear on multiple issues when a single implementation covers
several work items.

## Pull-request linking (automatic)

When a PR is opened on GitHub from a branch linked to one or more issues (or a
branch whose name contains an issue ID), the webhook **links the PR back to
Plane automatically**:

- Correlation is by **branch name** first. If that branch is linked to multiple
  issues, the PR appears on **all** of those issues.
- If no branch link exists, Plane falls back to an unambiguous issue key in the
  PR title/head branch.
- The PR appears in each linked issue's GitHub panel with its state
  (`open` / `merged` / `closed`)
- Link state updates are idempotent and timestamp-safe — stale webhook events
  never regress a newer state

## The issue GitHub panel

| Element                  | Behavior                                                |
| ------------------------ | ------------------------------------------------------- |
| **Create / link branch** | Creates a new branch or links an existing/shared branch |
| **Linked branches**      | Branch name and URL                                     |
| **Linked PRs**           | PR number, state, and URL                               |

> 💡 **Phase 2 (planned):** issue state transitions driven by PR events —
> `ready_for_review` moves the issue to In Review, merge moves it to Done,
> requested changes moves it back to Started. The linking itself (this page)
> already works end to end.

## Multiple repos per project

A project can have several repositories attached (for example a backend and a
frontend repo). Manage them in **Project Settings → GitHub**:

- **Attach repository** adds another enabled repository. A repository can be
  attached to a project only once; the picker lists only repos not yet attached
- The first repository attached becomes the **default**; later ones do not
  change it. **Set as default** on another row moves the default there
- **Remove** detaches a repository. Removing the default makes the **oldest
  remaining** repository the new default; removing the last one leaves the
  project without a repository (branch creation is hidden again)

What the default means:

- In the issue panel, **Create / link branch** shows a **repository selector**
  with the default pre-selected (unless your team's default repository applies,
  see below). A branch-create request that names no repository uses the default
- Pull requests are linked from **every** attached repository, default or not
- Linked branches and PRs show their repository name (the full `owner/repo`
  on hover) when the project has more than one repository or the issue has
  links from several repositories

## Teams and the team default repository

Workspace admins group members into teams in **Workspace Settings → Teams**
(admins and members can view the page; only admins can change it):

- **Create team**, **Rename**, **Delete**. Deleting a team removes its members
  from it; they can join another team right away
- A member belongs to **one team**. Adding a member who is already in another
  team asks for confirmation, then moves them
- Each team can have one **default repository**, picked from the workspace's
  enabled repositories (the picker is disabled until GitHub is connected and a
  repository is enabled)

Which repository a branch goes to when you create it from an issue:

1. The repository you pick in the selector (or `repo` in the API request)
2. Otherwise your team's default repository, **if this project has it
   attached**. A legacy mapping without a linked enabled repository matches by
   name (case-insensitive)
3. Otherwise the project default (the oldest mapping if none is marked default)

Step 2 is skipped when you are in no team, the team has no default, the
repository is disabled or removed, the installation is inactive, or you are
no longer an active workspace member. The issue panel pre-selects the same
repository the server would pick, and **Project Settings → GitHub** shows
"Team default for: …" under each repository that is a team's default.

## Time tracking (the other MRICS feature)

The fork also ships **work-log / time tracking**: issues carry a timer and
state-duration tracking (wall-clock time spent in each state), shown as
`Xh Ym` (or `Xd Zh` for 24+ hours). Duration display uses 24-hour calendar
days — state duration is wall-clock time, not effort.
