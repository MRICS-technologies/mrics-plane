# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Team repository per project: which project mapping a member's branch goes to.

Order when no repository is named: the mapping the member's team uses in this
project (ProjectTeamRepository, team attached to the project), else the project
default mapping. A team mapping whose repository is disabled on GitHub, or
whose installation is gone, is skipped. The rule lives only here; the mapping
list exposes it to the web picker.
"""

from django.db.models import Exists, OuterRef, Q

from plane.db.models import ProjectTeam, WorkspaceMember
from plane.db.models.integration.github_sync import ProjectTeamRepository, RepoProjectMapping


def _overrides(workspace_slug, project_id):
    # Overrides are hard-deleted with their mapping or team, or when the team
    # is detached; the deleted_at and link filters keep a missed cleanup path
    # falling back to the project default.
    # Legacy mappings have no repository row and stay usable.
    usable_repository = Q(mapping__repository__isnull=True) | Q(
        mapping__repository__is_enabled=True,
        mapping__repository__deleted_at__isnull=True,
        mapping__repository__installation__deleted_at__isnull=True,
        mapping__repository__installation__is_active=True,
    )
    attached = ProjectTeam.objects.filter(project_id=OuterRef("project_id"), team_id=OuterRef("team_id"))
    return ProjectTeamRepository.objects.filter(
        usable_repository,
        Exists(attached),
        workspace__slug=workspace_slug,
        project_id=project_id,
        mapping__deleted_at__isnull=True,
        team__deleted_at__isnull=True,
    )


def _my_overrides(workspace_slug, project_id, user):
    active_member = WorkspaceMember.objects.filter(workspace__slug=workspace_slug, member=user, is_active=True)
    return _overrides(workspace_slug, project_id).filter(
        Exists(active_member), team__team_members__member=user, team__team_members__deleted_at__isnull=True
    )


def pick_branch_mapping(workspace_slug, project_id, user, repo=None):
    """The project mapping a branch is created on, or None without mappings."""
    mappings = RepoProjectMapping.objects.filter(workspace__slug=workspace_slug, project_id=project_id)
    if repo:
        return mappings.filter(github_repo=repo).first()
    override = _my_overrides(workspace_slug, project_id, user).select_related("mapping").first()
    return override.mapping if override else mappings.order_by("-is_default", "created_at").first()


def mapping_team_hints(workspace_slug, project_id, user, mappings):
    """{mapping.id: {"default_for_teams": [{id, name}], "is_my_team_default": bool}} for this project."""
    overrides = list(_overrides(workspace_slug, project_id).select_related("team").order_by("team__name"))
    my_mapping_id = _my_overrides(workspace_slug, project_id, user).values_list("mapping_id", flat=True).first()
    return {
        mapping.id: {
            "default_for_teams": [
                {"id": str(override.team_id), "name": override.team.name}
                for override in overrides
                if override.mapping_id == mapping.id
            ],
            "is_my_team_default": mapping.id == my_mapping_id,
        }
        for mapping in mappings
    }
