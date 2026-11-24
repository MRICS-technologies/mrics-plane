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
  with the default pre-selected (unless your team has its own repository in
  this project, see below). A branch-create request that names no repository
  uses the default
- Pull requests are linked from **every** attached repository, default or not
- Linked branches and PRs show their repository name (the full `owner/repo`
  on hover) when the project has more than one repository or the issue has
  links from several repositories

## Teams and their repository per project

Workspace admins group members into teams in **Workspace Settings → Teams**
(admins and members can view the page; only admins can change it):

- **Create team**, **Rename**, **Delete**. Deleting a team removes its members
  from it (they can join another team right away) and its team defaults in
  every project
- A member belongs to **one team**. Adding a member who is already in another
  team asks for confirmation, then moves them

Which repository a team's branches go to is set **per project**, in
**Project Settings → GitHub → Team defaults** (project admins; shown once the
project has a repository attached). Each workspace team gets a select with
**Project default** and the repositories attached to this project, so the same
team can use repository A in one project and repository B in another. A
change is saved as soon as you pick it.

Which repository a branch goes to when you create it from an issue:

1. The repository you pick in the selector (or `repo` in the API request)
2. Otherwise the repository your team uses **in this project**
3. Otherwise the project default (the oldest mapping if none is marked default)

Step 2 is skipped when you are in no team, your team is on **Project
default** in this project, or you are no longer an active workspace member.
Removing a repository from the project, deleting the team or disconnecting
GitHub removes the team defaults that pointed at it, so those teams are back
on the project default. A team whose repository is disabled on GitHub
(removed from the GitHub App's repository access, or the installation is
suspended) also falls back to the project default; its choice is kept and
applies again once the installation is unsuspended or a workspace admin
enables the repository again (see [admin setup](admin-setup.md), step 4).
The issue panel pre-selects the same repository the
server would pick, and the repository list shows "Team default for: …" under
each repository that teams use in this project.

## Time tracking (the other MRICS feature)

The fork also ships **work-log / time tracking**: issues carry a timer and
state-duration tracking (wall-clock time spent in each state), shown as
`Xh Ym` (or `Xd Zh` for 24+ hours). Duration display uses 24-hour calendar
days — state duration is wall-clock time, not effort.
