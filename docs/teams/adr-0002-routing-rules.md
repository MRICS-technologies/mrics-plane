# ADR-0002: Routing rules (label / epic → team → leader)

## Status

Accepted

## Date

2026-11-26

## Context

Teams can be attached to projects, and each project-team link has an optional
leader ([ADR-0001](adr-0001-project-teams-and-membership-source.md)). The
product owner wants a per-project rule, "label X → team T" or "epic Y → team
T": a work item that gets label X, or is put directly under Y, gets T's leader
in that project as an assignee, and the work item's activity shows that the
rule did it, not the user. Writes come from the web, the public API (our MCP
server) and, later, GitHub; all of them must route the same way.

ADR-0001 sketched the rules. The decisions below supersede that sketch where
they differ: the rule points at the team, detaching disables instead of
deleting, and there is no priority.

Plane facts that shaped the design:

- Labels and assignees are written as delete-then-`bulk_create`
  (`IssueCreateSerializer.update`), and sub-issues are re-parented with
  `bulk_update`. Neither fires model signals.
- `ProjectTeam` is hard-deleted on detach and created again, with a new id,
  on re-attach.
- Deleting a label or a work item is a soft delete. Plane then runs an async
  cascade (`deletion_task.soft_delete_related_objects`) that soft-deletes every
  row pointing at it with `CASCADE`, including routing rules.

## Decision

1. **`ProjectRoutingRule(project, team, trigger_type, label | epic, enabled)`**:
   one row per rule, hard-deleted. The check constraint ties `label` or `epic`
   to `trigger_type`. There are two partial unique constraints:
   (project, label, team) and (project, epic, team), both for live rows. The
   same label can route to several teams.
2. **The rule points at the team, not at the `ProjectTeam` link.** The leader
   is read from the live `ProjectTeam(project, team)` each time a rule fires.
3. **Detach and team delete disable the team's rules.** They do it with one
   `update()` in the same transaction, under the team lock. Re-attaching does
   not re-enable them; an admin does. The API refuses to enable a rule whose
   team is detached.
4. **A deleted trigger is a computed state.** Nothing is hooked into Plane's
   delete paths:
   - The evaluator only matches live labels and live, non-archived epics.
   - The API reports `inactive_reason: label_deleted | epic_deleted`.
   - The API reads rules through `all_objects`, so rules that Plane's
     soft-delete cascade marked stay listed, inactive, and can still be
     deleted.
   - A hard delete cascades.
5. **One evaluator, in the request.** All routing happens in
   `apply_routing_rules(changes)` (`plane/services/teams/routing.py`):
   - Every write path calls it inside its own transaction, after writing its
     own labels, parent and assignees.
   - The callers are the app and public API issue serializers (create and
     update) and the sub-issues endpoint.
   - It runs a fixed number of bulk queries: rules, links, assignable leaders,
     current assignees, the bot, and two inserts.
6. **Every matching rule adds its leader** once, unless that leader is
   already assigned. There is no priority and no first-match. Assignees are
   never removed. A rule that can't assign anyone leaves an activity entry
   instead. That happens when the team is not attached, has no leader, or the
   leader fails Plane's assignee rule (active project member, role ≥ Member).
7. **The actor is an instance-wide bot,** `routing_rule_bot` (`is_bot`,
   `BotTypeEnum.ROUTING_RULE`):
   - It is created on first use, belongs to no workspace and has an unusable
     password.
   - Leaders are reported through Plane's own `issue_activity` task, sent
     after commit with the bot as actor, so leaders get Plane's normal
     activity, notification and webhooks.
8. **Direct children only.** Only a work item whose parent becomes the epic
   is routed, not that item's own sub-items.

## Alternatives considered

### Rule → `ProjectTeam` (the ADR-0001 sketch)

- One join less to find the leader.
- Rejected: detaching hard-deletes the link, so `CASCADE` would delete the
  rules, and re-attaching would leave the admin to re-create them. The other
  option is `SET_NULL`, which leaves rules pointing at nothing and still needs
  the team to show them.

### Delete rules on detach (cascade)

- Nothing to compute: a rule exists only while its team is attached.
- Rejected: an accidental detach would lose the configuration. Disabling costs
  one `update()` and a computed state in the API.

### Hooks in Plane's label / work item delete paths

- The rule row would hold the truth (`enabled = false`), with nothing computed.
- Cost: edits in several upstream views (label delete, issue delete, bulk
  delete, archive and unarchive, project archive). The async cascade would
  still race them.
- Rejected: two joins in the evaluator and the list query cost less.

### Django signals on `IssueLabel` / `Issue`

- No edits in Plane's write paths.
- Rejected: `bulk_create` and `bulk_update` fire no signals, so most paths
  (label writes, sub-issue re-parent) would be missed silently.

### Evaluate in the async `issue_activity` task

- One place that already sees every change, with no request latency.
- Cost:
  - It runs after commit and at least once, so it would have to be
    idempotent.
  - The response can't show the leader.
  - It would have to rebuild "labels gained" from request payloads whose keys
    differ per path (`label_ids` vs `labels`). Some payloads are wrong today:
    the sub-issues endpoint sends the child id as the old parent.
- Rejected: in the request, the evaluator sees the real before/after state,
  writes in the same transaction and adds a handful of queries.

### NULL actor, or a per-workspace bot

- NULL actor: no user row to manage. Rejected: Plane's activity and
  notification code expects an actor (`notifications` parses `actor_id` as a
  UUID), and the web would show a nameless row.
- Per-workspace bot (like Plane's `WORKSPACE_SEED` bot): it would need a
  `WorkspaceMember` row in every workspace, created up front or lazily, and
  every query that doesn't filter `member__is_bot` would count it.
  Rejected for one bot that belongs to no workspace. The activity API returns
  `actor_detail` from the user row, so no membership is needed for the name to
  show.

### Whole subtree under an epic

- Matches "everything in epic Y" more literally.
- Rejected for now: every re-parent would need a recursive walk, and moving a
  subtree would assign leaders to many items at once.

### Priority / first match wins (the sketch)

- One leader per work item.
- Rejected by the product owner: a work item labelled both Flutter and iOS
  should reach both leaders.

## Consequences

- **Upstream Plane edits:** one call plus the old-labels and old-parent
  capture in
  - `IssueCreateSerializer.create` / `.update` (`plane/app/serializers/issue.py`)
  - `IssueSerializer.create` / `.update` (`plane/api/serializers/issue.py`)
  - `SubIssuesEndpoint.post`. Its re-parent now runs in one transaction with
    the evaluator.
- **Coverage:** draft-to-issue, intake create and intake edit go through those
  serializers too, so intake items route while still in triage. Accepting an
  intake item changes no label or parent and routes nothing. A future write
  path must call the evaluator; GitHub writes neither labels nor parents today.
- **Not retroactive:** creating or enabling a rule changes no existing item.
- **Web assignee list:** leaders are assigned inside the user's request. The
  app create response includes them, but the app `PATCH` returns `204`, so the
  web only sees a leader after it refetches the work item. Plane replaces the
  whole assignee list on update. If the web sends its stale list in a later
  assignee change, it removes the leader; that is ordinary Plane behaviour.
- **Activity:** the "added assignee" activity is written asynchronously by
  Plane's task. "Couldn't assign" entries (`field="routing_rule"`) are written
  in the request. The web currently renders the first and shows nothing for
  the second (see [routing-rules.md](routing-rules.md)).
- **No `origin` is passed** to the activity task, like
  `issue_automation_task`: the request's own `issue_activity` call sets it for
  the same work item.
- **Detached-team entries are rare:** detach disables the rules under the team
  lock, and create and enable take the same lock. A "team is not attached"
  entry only appears if the link disappears another way.

## When to revisit

- Real epics (an epic issue type) arrive: restrict epic triggers to epics.
- Product asks for subtrees, priorities, or other actions (round-robin, assign
  the whole team).
- GitHub starts writing labels or parents: that path must call
  `apply_routing_rules`.
- Members can belong to several teams: revisit together with ADR-0001's
  source column.
- Rule evaluation measurably slows work item writes.
