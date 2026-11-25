# ADR-0001: Project teams and the membership source

## Status

Accepted

## Date

2026-11-25

## Context

Workspace teams (PR #44, one team per member) and a team's repository per
project (PR #45, `ProjectTeamRepository`) exist. The next step is to attach
teams to projects: an attached team's members become project members, team
changes keep that in sync, and detaching removes **only** the people the team
brought in. A project admin added individually, or someone added by hand, must
never be removed by a team. Each project-team link also gets an optional
leader, set per project, which future routing rules will assign.

Plane removes a project member by setting `ProjectMember.is_active = false`
and reactivates the same row when they come back.

## Decision

1. **`ProjectTeam(project, team, leader)`**, a link model with its own id,
   live-unique per (project, team) and hard-deleted. The leader is a nullable
   user foreign key on the link, so it is per project.
2. **`ProjectMember.source_team`**: a nullable foreign key to the team whose
   sync created or reactivated the membership. NULL means individual. A team
   only removes memberships it sourced, and never a project admin, workspace
   admin or bot (those are kept and turned individual). Every Plane path that
   adds someone by hand (add members, project join, invite accept, the
   `create_project_member` management command) clears it.
3. **One synchronous sync in the request**: `sync_project_members(project_ids,
user_ids)` in `plane/services/teams/project_sync.py` reconciles each
   (project, user) pair with a handful of bulk queries, inside the caller's
   transaction, while the caller holds the team row lock(s).

## Alternatives considered

### Link without its own id (plain many-to-many, or `project_ids` on the team)

- Cheaper by one column, and Django's M2M would hide the table.
- Rejected: the leader and future routing rules need a row to hang off, per
  project. Adding an id later means rewriting the table and its references.

### A separate source table (`ProjectMemberSource(project_member, team)`)

- Supports several sources per membership, which a member in several teams
  would need.
- Cost: one more table, a join in every sync and in every removal decision,
  and rows to keep consistent with `ProjectMember`.
- Rejected for now: one team per member means one source at most. If members
  can join several teams, move the column to such a table then.

### No stored source

- Remove every team member on detach, or infer "came from the team" from
  current team membership.
- Rejected: it cannot tell a person added by hand (who happens to be in the
  team) from one the team added, so detaching would remove individually added
  members.

### Celery job instead of an in-request sync

- Keeps large teams off the request path.
- Cost: eventual consistency (the API cannot return added/removed members),
  at-least-once delivery means the job must re-derive state anyway, and races
  with later team changes need the same locking plus ordering between jobs.
- Rejected: teams are small (a team POST is capped at 500 members) and the
  sync is a fixed number of bulk queries (an attach of a 10-member team runs
  19 queries in total, measured in the tests). Move it to a job if a single
  sync measurably slows requests.

## Consequences

- An active individual membership never becomes team-sourced. An inactive
  one (someone removed from the project) does when a team reactivates it, by
  design: the team brought them back, so it may remove them again. A
  team-sourced membership becomes individual when someone adds the person by
  hand, so a stale source cannot remove them later. This needed one-line edits
  in Plane's `ProjectMemberViewSet.create`,
  `UserProjectInvitationsViewset.create`, `ProjectJoinEndpoint.post` and the
  `create_project_member` command.
- The sync never changes the role of an active member.
- Workspace leave/rejoin is Plane's existing behaviour: leaving deactivates
  all project memberships; rejoining does not re-run the team sync.
- Removing a team-sourced member from a project by hand lasts until the next
  sync for that team (attach again, member re-added to the team).
- Team membership changes, attach/detach and team delete of the same team are
  serialized by the team row lock (attach and detach lock the project first),
  so two syncs for the same team never interleave.
- Plane's removal keeps issue assignments; so does a team removal.

Known limitations (Plane behaviour, not changed):

- Plane's member `PATCH` (`ProjectMemberViewSet.partial_update`) saves the
  whole row from an unlocked read, so a role change that races a team removal
  can write the membership back as active with its old source.
- The public API member `PATCH` (`/api/v1/.../members/<id>/`) accepts
  `member`, so it can re-point a team-sourced row to another user, who then
  inherits the source.

## Future: routing rules (not built)

Goal: "an issue with label X or in epic Y in project P goes to team T, and its
leader in P is assigned automatically." Sketch:

```
ProjectTeamRoutingRule (ProjectBaseModel)
  project_team  FK ProjectTeam, CASCADE   -- detach or team delete drops the rules
  match_kind    "label" | "epic"
  label         FK Label, null, CASCADE   -- set when match_kind = "label"
  epic          FK Issue, null, CASCADE   -- the epic, when match_kind = "epic"
  priority      int                       -- first match wins, lowest first;
                                          -- ties break by created_at
  action        "assign_leader"
  check: exactly one of label / epic matches match_kind
  unique live (project_team, label) where match_kind = "label"
  unique live (project_team, epic)  where match_kind = "epic"
  -- two partial constraints: one unique over all four columns would never
  -- fire, since Postgres treats the NULL label / epic as distinct
```

Evaluated on issue create and on label (or parent epic) change, in the issue
write path: find the first live rule of the issue's project that matches,
read its `ProjectTeam.leader`, and add them as an assignee if they are an
active project member. A link without a leader assigns nobody (no fallback to
another team). Rules hang off `ProjectTeam`, which is why the link has its own
id.
