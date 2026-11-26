# Routing rules

A project admin can route work to a team: "label **X** → team **T**" or
"epic **Y** → team **T**". When a work item gets label X, or is put directly
under Y, the leader of T **in this project** (see
[Team leader](project-teams.md#team-leader-per-project)) is added as an
assignee. The work item's activity shows that the routing rule did it, not
the user. This page covers the API; the settings UI is not built yet.

Design rationale: [ADR-0002](adr-0002-routing-rules.md).

## Behaviour

- **Triggers.**
  - A label that is new on the work item: created with it, or added later
    (the label was not there before the change).
  - A work item created under the epic, or moved under it.
  - Only direct children count. The children of a child don't.
  - The epic can be any work item of the project (Plane CE has no epic type).
- **Not triggers.**
  - Removing a label, or moving a work item away from the epic.
  - Saving a work item whose labels or parent didn't change.
  - Creating or enabling a rule does nothing to existing work items.
- **Action.**
  - For each matching enabled rule, the team's leader in this project is
    added as an assignee, unless they are already assigned.
  - Assignees are never removed, including the user's own assignees in the
    same save.
  - Several matching rules add each distinct leader once. There is no
    priority.
- **Can't assign.** If the team is not attached, has no leader, or the leader
  is not an active project member with role Member or Admin (Plane's assignee
  rule), nobody is assigned for that rule. An activity entry explains why
  (see below).
- **Team detached or deleted.** Its rules in that project (or in every
  project, for a delete) are disabled, not deleted. Re-attaching does not
  re-enable them: an admin enables them again.
- **Label or epic deleted (or the epic archived).**
  - The rule stops matching and shows as inactive.
  - It can be deleted but not enabled.
  - Unarchiving the epic makes the rule active again, unless it was disabled.

### Example

Project **Mobile** has team **Flutter** attached, with **Ahmed** as its
leader in Mobile, and the rule `label "Flutter" → team Flutter`.

1. Sara creates "Login screen" with labels Flutter and UI, and assigns
   herself.
2. Sara and Ahmed are both assignees. Sara's own activity shows her changes;
   a separate entry by **Routing rule** reads "added a new assignee Ahmed".
3. Ahmed gets Plane's usual "assigned" notification, triggered by
   "Routing rule".
4. Removing Flutter later keeps Ahmed assigned. Adding Flutter back does
   nothing, because he is already assigned.
5. If Flutter had no leader in Mobile, nobody would be added, and the work
   item would get the entry
   `routing rule matched (label "Flutter" → team Flutter), team has no leader`.

## API

All paths are under `/api/workspaces/<workspace-slug>/projects/<project-id>/`.
Permissions follow Plane's project rules (`allow_permission`), as for project
teams. A workspace admin who is not a member of the project gets `403`.

| Method   | Path                       | Body                | Who                   | Success |
| -------- | -------------------------- | ------------------- | --------------------- | ------- |
| `GET`    | `routing-rules/`           |                     | project admin, member | `200`   |
| `POST`   | `routing-rules/`           | see below           | project admin         | `201`   |
| `PATCH`  | `routing-rules/<rule-id>/` | `{"enabled": bool}` | project admin         | `200`   |
| `DELETE` | `routing-rules/<rule-id>/` |                     | project admin         | `204`   |

Project guests, users outside the project and outsiders get `403`; project
members get `403` on writes.

**Row shape.** `GET` returns a list ordered by `created_at`. `POST` and
`PATCH` return one row.

```json
{
  "id": "<rule id>",
  "trigger_type": "label",
  "label": { "id": "<label id>", "name": "Flutter", "color": "#00aaff" },
  "epic": null,
  "team": { "id": "<team id>", "name": "Flutter" },
  "leader_id": "<user id, or null>",
  "team_attached": true,
  "enabled": true,
  "is_active": true,
  "inactive_reason": null,
  "created_at": "2026-11-26T08:00:00Z"
}
```

An epic rule has `"label": null` and
`"epic": {"id", "name", "sequence_id", "project_identifier"}`.

- `leader_id` is the team's current leader in this project. It is `null`
  when the team is not attached, has no leader, or the leader has left the
  team or the workspace (the same rule as the project teams list).
- `is_active` is true when the rule is enabled, the team is attached and the
  trigger is live.
- `inactive_reason` is `null` or one of the values below. The first that
  applies wins:

| Reason          | Meaning                                   | How to fix                    |
| --------------- | ----------------------------------------- | ----------------------------- |
| `label_deleted` | The label was deleted                     | Delete the rule               |
| `epic_deleted`  | The epic was deleted or archived          | Delete the rule, or unarchive |
| `team_detached` | The team is not attached (or was deleted) | Attach the team, then enable  |
| `disabled`      | `enabled` is false                        | `PATCH {"enabled": true}`     |

**`POST routing-rules/`** creates a rule. It changes no existing work item.

```json
{ "trigger_type": "label", "label_id": "<uuid>", "team_id": "<uuid>" }
{ "trigger_type": "epic", "epic_id": "<uuid>", "team_id": "<uuid>" }
```

`400` returns errors by field:

| Field          | When                                                                                                              |
| -------------- | ----------------------------------------------------------------------------------------------------------------- |
| `trigger_type` | Missing, or not `label` / `epic`                                                                                  |
| `label_id`     | Missing or malformed for a label rule; sent with an epic rule; not a live label of this project                   |
| `epic_id`      | Missing or malformed for an epic rule; sent with a label rule; not a live, non-archived work item of this project |
| `team_id`      | Missing, unknown, deleted, or a team of another workspace (`"Must be a team of this workspace."`)                 |
| `team_id`      | A team of this workspace that is not attached (`"Attach the team to this project first."`)                        |

A `null` id for the other trigger is accepted.

`409 {"detail": "This rule already exists.", "id": "<existing rule id>"}`
when a live rule already has the same trigger and team. The same label or epic
may route to several teams.

**`PATCH routing-rules/<rule-id>/`** takes `{"enabled": true|false}` and
nothing else.

- Any other key gets `400 {"<key>": ["This field can't be changed."]}`.
- Enabling an inactive rule gets `400 {"enabled": ["<reason>"]}`, with one of
  these reasons:
  - "Attach the team to this project first."
  - "The label was deleted."
  - "The epic was deleted or archived."
- A rule of another project, or an unknown id, gets `404`.

**`DELETE routing-rules/<rule-id>/`** deletes the rule for good. `404` when
it doesn't exist in this project.

## Activity entries

The issue activity endpoint (`GET .../issues/<id>/history/`) returns two kinds
of entries from routing rules. Both have the routing rule bot as actor. The
bot is one user per instance: `username` `routing_rule_bot`, `display_name`
and `first_name` "Routing rule", `is_bot: true`. It belongs to no workspace
and can't sign in.

**Leader added.** Plane's own `issue_activity` task writes this entry after
the request commits. It is the same entry as when a user adds an assignee,
with the same notification. It sends no issue webhook: a webhook consumer
sees the user's label or parent change, not the bot's assignee change.

```json
{
  "field": "assignees",
  "verb": "updated",
  "comment": "added assignee ",
  "old_value": "",
  "new_value": "Ahmed",
  "new_identifier": "<leader id>",
  "actor": "<bot id>",
  "actor_detail": {
    "id": "<bot id>",
    "first_name": "Routing rule",
    "last_name": "",
    "display_name": "Routing rule",
    "is_bot": true,
    "avatar": "",
    "avatar_url": null
  }
}
```

The leader is also subscribed to the work item (Plane does this for every
added assignee); the bot is not.

**Rule matched, nobody assigned.** This entry is written in the request,
without a notification:

```json
{
  "field": "routing_rule",
  "verb": "updated",
  "comment": "routing rule matched (label \"Flutter\" → team Flutter), team has no leader",
  "old_value": null,
  "new_value": null,
  "actor": "<bot id>",
  "actor_detail": { "display_name": "Routing rule", "is_bot": true }
}
```

The comment is `routing rule matched (<trigger> → team <team name>), <reason>`:

- `<trigger>` is `label "<name>"` or `epic "<work item name>"`.
- `<reason>` is one of:
  - `team has no leader`
  - `team is not attached to the project`
  - `leader can't be assigned (not an active project member)`

### How the web renders them today (no web changes yet)

The web asks for `?activity_type=issue-property`
(`apps/web/services/issue/issue_activity.service.ts:32-34`). The API filters
out only `comment`, `vote`, `reaction` and `draft` rows
(`apps/api/plane/app/views/issue/activity.py:48-60`), so both kinds of entry
reach the web.

- **Leader added:** the web shows "**Routing rule** added a new assignee
  **Ahmed**".
  - `field="assignees"` dispatches to `IssueAssigneeActivity`
    (`apps/web/components/issues/issue-detail/issue-activity/activity/activity-list.tsx:63-64`).
  - The wording comes from `old_value === ""`
    (`.../activity/actions/assignee.tsx:34`), and the leader's name links to
    their profile (`:36-41`).
  - The actor name is `actor_detail.display_name`, read from the activity
    itself, not from the workspace member map
    (`.../activity/actions/helpers/issue-user.tsx:33-36`). The bot is not a
    workspace member, but its name still shows. The name links to
    `/<slug>/profile/<bot id>`, a profile page with nothing on it.
  - The notification card shows "Routing rule added assignee Ahmed".
    `is_bot` actors show their `first_name`
    (`apps/web/components/workspace-notifications/sidebar/notification-card/content.tsx:181`).
- **Rule matched, nobody assigned:** the web shows nothing. It doesn't crash.
  - `activity-list.tsx:94-95` returns `null` for an unknown field.
  - The store classes the row as the "Updates" filter type
    (`apps/web/store/issue/issue-details/activity.store.ts:102-109`), so it is
    kept in the list. Two small side effects:
    - When it is the last row, the timeline connector of the row above runs
      past it, because `getEnds` counts the hidden row
      (`.../issue-activity/activity-comment-root.tsx:73-74`).
    - When it is the only row, the list is blank instead of showing the empty
      state (`:60`).
  - To show it, add a `case "routing_rule":` to `activity-list.tsx` that
    renders `activity.comment`.

**For the front end:** the app `PATCH .../issues/<id>/` returns `204`, so the
web learns about an added leader only when it refetches the work item. Plane
replaces the whole assignee list on update. If the web later saves assignees
from a stale list, it removes the leader. Refetch the work item after
changing its labels or parent.

## Write paths covered

Every write path calls the same evaluator (`apply_routing_rules` in
`apps/api/plane/services/teams/routing.py`) inside its transaction:

| Path                                                                   | Covered | How                                                        |
| ---------------------------------------------------------------------- | ------- | ---------------------------------------------------------- |
| Web: create / `PATCH` work item (`label_ids`, `parent_id`)             | yes     | `IssueCreateSerializer.create` / `.update`                 |
| Web: add existing work items as sub-items (`POST .../sub-issues/`)     | yes     | `SubIssuesEndpoint.post` (only items whose parent changes) |
| Web: draft → work item (`POST workspaces/<slug>/draft-to-issue/<id>/`) | yes     | `IssueCreateSerializer.create`                             |
| Web: intake create / edit                                              | yes     | `IssueCreateSerializer` (routes while still in triage)     |
| Public API v1 / MCP: create / `PATCH` work item (`labels`, `parent`)   | yes     | `plane/api/serializers/issue.py` `IssueSerializer`         |
| Public API v1: intake edit                                             | yes     | `IssueSerializer.update`                                   |
| Intake accept (app, v1)                                                | n/a     | Changes state only, no label or parent                     |
| Intake create (v1, public space form), space intake edit               | n/a     | Name, description and priority only                        |
| Archive / unarchive, bulk dates, relations, cycles, modules            | n/a     | No label or parent change                                  |
| GitHub                                                                 | n/a     | No GitHub path changes labels or parents today (see below) |

**GitHub.** The webhook handles `pull_request`, `installation` and
`installation_repositories` events. It acknowledges `labeled` and other
pull request actions without any state change
(`apps/api/plane/app/views/github_sync.py:66-67`). On the work item side it
only writes PR links (`IssueGitLink`, with the PR's own state). When GitHub starts writing labels or parents, that path must
call `apply_routing_rules` like the others. MCP and other public API writes
are already covered.

The `IssueCreateSerializer` in `plane/space/serializer/issue.py` is not used
by any view, so it is not hooked.

## Code map

| Concern                         | Location                                                                                 |
| ------------------------------- | ---------------------------------------------------------------------------------------- |
| Evaluator and bot user          | `apps/api/plane/services/teams/routing.py`                                               |
| Endpoints                       | `apps/api/plane/app/views/project/routing_rule.py`                                       |
| Model (`ProjectRoutingRule`)    | `apps/api/plane/db/models/project.py`                                                    |
| Disable on detach / team delete | `apps/api/plane/app/views/project/team.py`, `apps/api/plane/app/views/workspace/team.py` |
| Contract tests                  | `apps/api/plane/tests/contract/api/test_workspace_teams.py`                              |

## Deploy notes

- **One migration:** `db.0134_project_routing_rule`.
  - It creates the empty `project_routing_rules` table with its check
    constraint, its two partial unique indexes and its foreign key indexes.
  - No data changes.
  - squawk reports three warnings, all normal for a new table: `varchar(10)`
    instead of `text` (Plane's `CharField` convention), and no
    `lock_timeout` / `statement_timeout`. Adding the foreign keys takes a brief
    `SHARE ROW EXCLUSIVE` lock on `users`, `issues`, `labels`, `projects`,
    `teams` and `workspaces`. The new table is empty, so the check is instant,
    but the lock waits behind long transactions on those tables.
- **No environment variables, no new services.**
- **Bot user:** `routing_rule_bot` is created the first time a rule fires,
  with a random `@plane.invalid` email. It needs no setup.
