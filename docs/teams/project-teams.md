# Project teams

Workspace teams (**Workspace Settings → Teams**, one team per member) can be
attached to projects. An attached team's members become project members, and
team changes keep those memberships in sync. Each project-team link has an
optional **leader**, set per project. This page covers the API; the web UI is
not built yet.

Design rationale: [ADR-0001](adr-0001-project-teams-and-membership-source.md).

## What attaching does

Attaching a team to a project (project admins) makes every team member who is
an active workspace member a project member:

- **New to the project**: added with their **workspace role** as project role
  (workspace member → Member 15, guest → Guest 5, admin → Admin 20; Plane allows
  no other project role for workspace admins and guests). They get their
  project user properties and Plane's "added to project" email, as with
  Plane's own **Add members**.
- **Previously removed** from the project (inactive membership): reactivated,
  with their workspace role.
- **Already an active member**: nothing changes, not even the role. The
  membership stays individual.

While the team is attached, the project follows the team:

| Team change                    | Project membership                                                                         |
| ------------------------------ | ------------------------------------------------------------------------------------------ |
| Member added to the team       | Added to every project the team is attached to                                             |
| Member moved to another team   | Added to the new team's projects; removed from the old team's projects (safety rule below) |
| Member removed from the team   | Removed from the team's projects (safety rule)                                             |
| Team deleted                   | Its members removed from all its projects (safety rule); its links are deleted             |
| Team detached from the project | Its members removed from that project (safety rule)                                        |

Detaching also deletes the team's repository choice in that project (GitHub
**Team defaults**).

## Membership source and the removal safety rule

`ProjectMember.source_team` records where a membership came from:

- **NULL, individual**: every membership that existed before migration 0133,
  and every membership added by hand: Plane's **Add members**, joining a
  project, accepting a project invite, the `create_project_member` management
  command. Adding by hand also clears the source of an existing team
  membership. The source is not writable through any API.
- **Set**: the team sync created or reactivated the membership.

A team only ever removes memberships it sourced. When a member's attached team
is gone (detached, deleted, or they left it), a team-sourced membership is:

- **kept** and turned individual (source cleared) when the member is a
  **project admin**, a **workspace admin**, or a **bot**;
- otherwise **removed** the way Plane removes a project member
  (`is_active = false`). Issue assignments are not touched (see below).

Individual memberships are never touched by teams.

Things to know:

- Removing a team-sourced member from the project by hand lasts until the next
  sync for that team: attaching the team again or re-adding them to the team
  brings them back. To keep someone out, remove them from the team.
- Leaving the workspace deactivates all of a user's project memberships
  (Plane's existing behaviour). Rejoining the workspace does not bring the
  team memberships back until a sync touches them (attach again, or re-add
  them to the team).
- Members who left the workspace are not added and are not listed.

## Team leader (per project)

Each link (team attached to a project) has one optional leader. The same team
can have a different leader in each project.

- The leader must be a member of that team and an active workspace member.
- Leaving the team (removed, or moved to another team) clears them as leader of
  that team in every project.
- Detaching the team or deleting it removes the link, and the leader with it.
- A leader who has since left the workspace reads as `"leader_id": null`.

The leader is not used anywhere yet; see the routing rules sketch in the ADR.

## API

All paths are under `/api/workspaces/<workspace-slug>/projects/<project-id>/`.
Permissions follow Plane's project rules (`allow_permission`): a project admin,
or a workspace admin who is a member of the project. A workspace admin who is
not a member of the project gets `403`, as on every other project endpoint.

| Method   | Path               | Body                              | Who                   | Success                           |
| -------- | ------------------ | --------------------------------- | --------------------- | --------------------------------- |
| `GET`    | `teams/`           |                                   | project admin, member | `200`                             |
| `POST`   | `teams/`           | `{"team_id": "<uuid>"}`           | project admin         | `201` new, `200` already attached |
| `PATCH`  | `teams/<team-id>/` | `{"leader_id": "<uuid>" \| null}` | project admin         | `200`                             |
| `DELETE` | `teams/<team-id>/` |                                   | project admin         | `200`                             |

Project guests, users outside the project and outsiders get `403`.

**Row shape** (`GET` returns a list ordered by team name):

```json
{
  "id": "<project-team id>",
  "team": { "id": "<team id>", "name": "Frontend", "member_ids": ["<user id>"] },
  "leader_id": "<user id, or null>",
  "created_at": "2026-11-25T08:00:00Z"
}
```

`member_ids` lists team members who are active workspace members (as on the
Teams page).

**`POST teams/`** attaches the team and runs the sync. Response: the row shape
plus `"added_member_ids": [...]` (members added or reactivated). Attaching a
team that is already attached returns `200` and runs the sync again (it is
idempotent). `400` for a missing or malformed `team_id`; `404` for an unknown
team, a team of another workspace or a deleted team.

**`PATCH teams/<team-id>/`** sets or clears (`null`) the leader. Returns the row
shape. `400 {"leader_id": ["Must be a member of this team."]}` when the user is
not a member of the team or not an active workspace member; `400` for a
malformed body; `404` when the team is not attached to the project.

**`DELETE teams/<team-id>/`** detaches the team: deletes the link and the
team's repository in this project, then runs the sync.

```json
{ "removed_member_ids": ["<user id>"], "kept_member_ids": ["<user id>"] }
```

`kept_member_ids` are the team's members (and anyone the team had added here)
who are still active project members after the detach. `404` when the team is
not attached.

**Workspace teams** (`/api/workspaces/<workspace-slug>/teams/...`): the
response shape is unchanged. It lists no projects (that would show secret
project ids to every workspace member) and no leader.

**GitHub team defaults** (`.../github/team-repositories/`): only teams attached
to the project are listed, and `PUT` for a team of the workspace that is not
attached is `400 {"team_id": ["Attach the team to this project first."]}`. The
branch resolver also ignores a team repository whose team is not attached.

## Issue assignees of removed members (Plane behaviour, unchanged)

Removing a project member (by hand or by a team) only sets
`ProjectMember.is_active = false`:

- `IssueAssignee` rows are kept: removal never touches them
  (`apps/api/plane/app/views/project/member.py:346`, `:374`; no signal or task
  reacts to `is_active`).
- The issue lists still return them in `assignee_ids`
  (`apps/api/plane/utils/grouper.py:49-57`, unfiltered). Issue detail filters
  with `assignees__member_project__is_active=True`
  (`apps/api/plane/app/views/issue/base.py:663-671`), which matches an active
  membership in **any** project, not this one.
- They cannot be newly assigned: the app API silently drops them
  (`apps/api/plane/app/serializers/issue.py:159-166`), and since an update
  replaces the whole assignee set (`:296-313`), saving the issue's assignees
  removes them; the public API rejects them with a 400
  (`apps/api/plane/api/serializers/issue.py:125-140`).
- The web still shows their avatar (it resolves users from the workspace
  member map, `apps/web/components/dropdowns/member/avatar.tsx:36-39`) but the
  assignee picker only offers active project members
  (`apps/web/components/dropdowns/member/member-select.tsx:129-133`); an
  existing assignment shows pinned and can be unchecked
  (`packages/blocks/src/select/root.tsx:230-237`).

## Code map

| Concern                               | Location                                                    |
| ------------------------------------- | ----------------------------------------------------------- |
| Membership sync (the only place)      | `apps/api/plane/services/teams/project_sync.py`             |
| Project team endpoints                | `apps/api/plane/app/views/project/team.py`                  |
| Team endpoints (call the sync)        | `apps/api/plane/app/views/workspace/team.py`                |
| Models (`ProjectTeam`, `source_team`) | `apps/api/plane/db/models/project.py`                       |
| Contract tests                        | `apps/api/plane/tests/contract/api/test_workspace_teams.py` |

Every caller of the sync runs in a transaction and holds the row lock of each
team involved (attach and detach lock the project first, then the team), so
changes to the same team are serialized.

## Deploy notes

- **One migration**: `db.0133_project_team_leader_member_source`. It adds the
  nullable `project_members.source_team_id` (foreign key to `teams`, indexed),
  creates `project_teams`, and **backfills** a link for every live team
  repository (`project_team_repositories`) whose team and project are live, so
  the team defaults configured since 0132 stay listed. It changes no
  memberships.
- **No environment variables, no new services.**
- **Locks**: adding the column, its foreign key and its index briefly blocks
  writes to `project_members` (squawk flags the non-`CONCURRENTLY` index and
  the validated foreign key). The column is all NULL and the table is small,
  so this takes well under a second; run it outside peak hours if
  `project_members` has grown large.
- **After deploy**: **Project Settings → GitHub → Team defaults** lists only
  the teams attached to the project. Until the **Project Settings → Teams** UI
  ships, a project admin attaches a team through the API:

  ```bash
  curl -X POST "https://<plane-host>/api/workspaces/<workspace-slug>/projects/<project-id>/teams/" \
    -H "Cookie: session-id=<project admin's session cookie>" \
    -H "Content-Type: application/json" -d '{"team_id": "<team-id>"}'
  ```

  The session cookie comes from a browser signed in as a project admin. `201`
  attaches the team; `200` means it was already attached and the sync ran
  again.

- **Backfilled teams**: teams that already had a team default were attached by
  the 0133 backfill, but their members were not synced. Attach each of them
  again (the same `POST`, `200`, idempotent) to add their members to the
  project.
- **Rollback**: with this code still deployed (it ships the 0133 file), run
  `python manage.py migrate db 0132_team_member_project_team_repository`, which
  drops the table and the column (the backfill's reverse is a no-op and the
  sources are lost), then deploy the previous code.
