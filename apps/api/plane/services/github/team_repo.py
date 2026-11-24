# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Team repository per project: which project mapping a member's branch goes to.

Order when no repository is named: the mapping the member's team uses in this
project (ProjectTeamRepository), else the project default mapping. The rule
lives only here; the mapping list exposes it to the web picker.
"""

from django.db.models import Exists

from plane.db.models import WorkspaceMember
from plane.db.models.integration.github_sync import ProjectTeamRepository, RepoProjectMapping


def _overrides(workspace_slug, project_id):
    # Overrides are hard-deleted with their mapping or team; the two filters
    # keep a missed cleanup path falling back to the project default.
    return ProjectTeamRepository.objects.filter(
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


def team_override_mapping(workspace_slug, project_id, user):
    """The live mapping the user's team uses in this project, or None."""
    override = _my_overrides(workspace_slug, project_id, user).select_related("mapping").first()
    return override.mapping if override else None


def pick_branch_mapping(workspace_slug, project_id, user, repo=None):
    """The project mapping a branch is created on, or None without mappings."""
    mappings = RepoProjectMapping.objects.filter(workspace__slug=workspace_slug, project_id=project_id)
    if repo:
        return mappings.filter(github_repo=repo).first()
    return (
        team_override_mapping(workspace_slug, project_id, user)
        or mappings.order_by("-is_default", "created_at").first()
    )


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
