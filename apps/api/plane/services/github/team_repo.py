# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Team default repository: which project mapping a member's branch goes to.

Order when no repository is named: the member's team default repository if
the project has it attached, else the project default mapping. The matching
rule lives only here; the mapping list exposes it to the web picker.
"""

from plane.db.models import Team, WorkspaceMember
from plane.db.models.integration.github_app import GithubEnabledRepository
from plane.db.models.integration.github_sync import RepoProjectMapping


def usable_repositories(workspace_slug):
    """Enabled repositories of the workspace's live, active installation."""
    return GithubEnabledRepository.objects.filter(
        is_enabled=True,
        installation__deleted_at__isnull=True,
        installation__is_active=True,
        installation__workspace__slug=workspace_slug,
    )


def team_default_repository(workspace_slug, user):
    """The usable default repository of the user's team, or None."""
    if not WorkspaceMember.objects.filter(workspace__slug=workspace_slug, member=user, is_active=True).exists():
        return None
    my_team = Team.objects.filter(
        workspace__slug=workspace_slug, team_members__member=user, team_members__deleted_at__isnull=True
    )
    return usable_repositories(workspace_slug).filter(default_for_teams__in=my_team).first()


def mapping_matches(mapping, repository):
    """A mapping points at the repository by FK; legacy rows (no FK) by name."""
    if mapping.repository_id:
        return mapping.repository_id == repository.id
    return mapping.github_repo.lower() == repository.full_name.lower()


def pick_branch_mapping(workspace_slug, project_id, user, repo=None):
    """The project mapping a branch is created on, or None without mappings."""
    mappings = RepoProjectMapping.objects.filter(workspace__slug=workspace_slug, project_id=project_id)
    if repo:
        return mappings.filter(github_repo=repo).first()
    ordered = list(mappings.order_by("-is_default", "created_at"))
    team_repo = team_default_repository(workspace_slug, user)
    if team_repo:
        for mapping in ordered:
            if mapping_matches(mapping, team_repo):
                return mapping
    return ordered[0] if ordered else None


def mapping_team_hints(workspace_slug, user, mappings):
    """{mapping.id: {"default_for_teams": [{id, name}], "is_my_team_default": bool}}."""
    teams = list(
        Team.objects.filter(workspace__slug=workspace_slug, default_repository__in=usable_repositories(workspace_slug))
        .select_related("default_repository")
        .order_by("name")
    )
    my_repo = team_default_repository(workspace_slug, user)
    return {
        mapping.id: {
            "default_for_teams": [
                {"id": str(team.id), "name": team.name}
                for team in teams
                if mapping_matches(mapping, team.default_repository)
            ],
            "is_my_team_default": bool(my_repo and mapping_matches(mapping, my_repo)),
        }
        for mapping in mappings
    }
