# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Project membership that comes from teams.

A team attached to a project (ProjectTeam) makes its members project members.
sync_project_members() is the only place that adds or removes them. Callers
run it in their transaction, after changing team members or links, while
holding the lock of every team involved (attach and detach lock the project
first, then the team).

Removal safety: only a membership the sync created or reactivated
(ProjectMember.source_team set) is ever removed, and never a project admin, a
workspace admin or a bot: they stay as individual members. Adding someone by
hand clears the source, so no team removes them later.
"""

from django.db import transaction
from django.db.models import F, Min
from django.utils import timezone

from plane.bgtasks.project_add_user_email_task import project_add_user_email
from plane.db.models import ProjectMember, ProjectTeam, ProjectUserProperty, Team, WorkspaceMember
from plane.utils.host import base_host

ADMIN = 20


def locked_teams(slug):
    """Live teams of the workspace, row-locked (in id order) when evaluated."""
    return Team.objects.select_for_update(no_key=True, of=("self",)).filter(workspace__slug=slug).order_by("pk")


def sync_team_members(workspace_id, user_ids, *, team_id=None, actor, request):
    """After user_ids joined team_id, or left their team: sync the projects
    team_id is attached to and every project where they hold a team-sourced
    membership (the only ones a lost team can change)."""
    user_ids = list(user_ids)
    project_ids = set(
        ProjectMember.objects.filter(
            workspace_id=workspace_id, member_id__in=user_ids, is_active=True, source_team__isnull=False
        ).values_list("project_id", flat=True)
    )
    if team_id:
        project_ids |= set(ProjectTeam.objects.filter(team_id=team_id).values_list("project_id", flat=True))
    return sync_project_members(project_ids, user_ids, actor=actor, request=request)


def sync_project_members(project_ids, user_ids, *, actor, request):
    """Reconcile every (project, user) pair with the teams attached to the
    projects. Returns {"added": user ids, "removed": user ids}."""
    project_ids, user_ids = list(project_ids), list(user_ids)
    if not project_ids or not user_ids:
        return {"added": set(), "removed": set()}

    links = list(
        ProjectTeam.objects.filter(
            project_id__in=project_ids,
            team__deleted_at__isnull=True,
            team__team_members__member_id__in=user_ids,
            team__team_members__deleted_at__isnull=True,
        ).values_list("project_id", "team__team_members__member_id", "workspace_id", "team_id")
    )
    # Locked so a concurrent individual add (which clears the source) wins.
    rows = {
        (row.project_id, row.member_id): row
        for row in ProjectMember.objects.select_for_update(of=("self",))
        .filter(project_id__in=project_ids, member_id__in=user_ids)
        .annotate(is_bot=F("member__is_bot"))
        .order_by("pk")
    }
    workspace_ids = {link[2] for link in links} | {row.workspace_id for row in rows.values()}
    roles = {
        (workspace_id, member_id): role
        for workspace_id, member_id, role in WorkspaceMember.objects.filter(
            workspace_id__in=workspace_ids, member_id__in=user_ids, is_active=True
        ).values_list("workspace_id", "member_id", "role")
    }
    # One team per member, so at most one attached team per pair.
    team_of = {(p, u): (ws, team_id) for p, u, ws, team_id in links if (ws, u) in roles}

    created, changed, added = [], [], []
    for (project_id, user_id), (workspace_id, team_id) in team_of.items():
        row = rows.get((project_id, user_id))
        # The workspace role: the default for a member, and the only project
        # role Plane allows a workspace admin or guest.
        role = roles[workspace_id, user_id]
        if row is None:
            row = ProjectMember(
                project_id=project_id,
                workspace_id=workspace_id,
                member_id=user_id,
                role=role,
                source_team_id=team_id,
                created_by=actor,
            )
            created.append(row)
        elif not row.is_active:
            row.is_active, row.role, row.source_team_id = True, role, team_id
            changed.append(row)
        else:
            # Already a member: the role is never changed. A team-sourced
            # membership now comes from this team; an individual one stays so.
            if row.source_team_id not in (None, team_id):
                row.source_team_id = team_id
                changed.append(row)
            continue
        added.append(row)

    removed = set()
    for pair, row in rows.items():
        if pair in team_of or not row.is_active or row.source_team_id is None:
            continue
        row.source_team_id = None
        if row.role != ADMIN and roles.get((row.workspace_id, row.member_id)) != ADMIN and not row.is_bot:
            # Removed the way Plane removes a project member; issue assignments stay.
            row.is_active = False
            removed.add(row.member_id)
        changed.append(row)

    # ponytail: a concurrent individual add of the same new pair wins the
    # insert; the pair is still reported (and emailed) as added here.
    ProjectMember.objects.bulk_create(created, ignore_conflicts=True)
    now = timezone.now()
    for row in changed:
        row.updated_at, row.updated_by = now, actor
    ProjectMember.objects.bulk_update(changed, ["is_active", "role", "source_team", "updated_at", "updated_by"])
    if added:
        _create_user_properties(added, actor)
        host, ids = base_host(request=request, is_app=True), [row.id for row in added]
        transaction.on_commit(lambda: [project_add_user_email.delay(host, pk, actor.id) for pk in ids])
    return {"added": {row.member_id for row in added}, "removed": removed}


def _create_user_properties(rows, actor):
    # Same as ProjectMemberViewSet.create: bulk inserts skip ProjectMember.save(),
    # which creates the row with the member's lowest sort order minus 10000.
    lowest = {
        (item["workspace_id"], item["user_id"]): item["lowest"]
        for item in ProjectUserProperty.objects.filter(
            workspace_id__in={row.workspace_id for row in rows}, user_id__in={row.member_id for row in rows}
        )
        .values("workspace_id", "user_id")
        .annotate(lowest=Min("sort_order"))
    }
    ProjectUserProperty.objects.bulk_create(
        [
            ProjectUserProperty(
                project_id=row.project_id,
                workspace_id=row.workspace_id,
                user_id=row.member_id,
                sort_order=(
                    lowest[row.workspace_id, row.member_id] - 10000
                    if (row.workspace_id, row.member_id) in lowest
                    else 65535
                ),
                created_by=actor,
            )
            for row in rows
        ],
        ignore_conflicts=True,
    )
