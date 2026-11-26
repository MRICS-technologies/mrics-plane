# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers.team import (
    ProjectTeamAttachSerializer,
    ProjectTeamLeaderSerializer,
    active_team_members,
    serialize_project_team,
)
from plane.db.models import (
    Project,
    ProjectMember,
    ProjectRoutingRule,
    ProjectTeam,
    ProjectTeamRepository,
    TeamMember,
)
from plane.services.teams.project_sync import locked_teams, sync_project_members
from ..base import BaseAPIView


def _links(slug, project_id):
    return (
        ProjectTeam.objects.filter(workspace__slug=slug, project_id=project_id, team__deleted_at__isnull=True)
        .select_related("team")
        .prefetch_related(Prefetch("team__team_members", queryset=active_team_members()))
    )


def _lock_team(slug, team_id):
    return locked_teams(slug).filter(pk=team_id).first()


def _lock_project_and_team(slug, project_id, team_id):
    # Project first, then team: the order of the team repository writes too.
    project = (
        Project.objects.select_for_update(no_key=True, of=("self",)).filter(workspace__slug=slug, pk=project_id).first()
    )
    return project, _lock_team(slug, team_id)


class ProjectTeamEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id):
        return Response([serialize_project_team(link) for link in _links(slug, project_id).order_by("team__name")])

    @allow_permission([ROLE.ADMIN])
    def post(self, request, slug, project_id):
        serializer = ProjectTeamAttachSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            project, team = _lock_project_and_team(slug, project_id, serializer.validated_data["team_id"])
            if not project or not team:
                return Response(status=status.HTTP_404_NOT_FOUND)
            link, created = ProjectTeam.objects.get_or_create(project=project, team=team)
            # Attaching again re-runs the sync: it is idempotent.
            members = TeamMember.objects.filter(team=team).values_list("member_id", flat=True)
            added = sync_project_members([project.id], members, actor=request.user, request=request)["added"]
            # Read under the locks, before a concurrent detach can delete the link.
            data = serialize_project_team(_links(slug, project_id).get(pk=link.pk))
        data["added_member_ids"] = sorted(str(member_id) for member_id in added)
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ProjectTeamDetailEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN])
    def patch(self, request, slug, project_id, team_id):
        serializer = ProjectTeamLeaderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        leader_id = serializer.validated_data["leader_id"]
        with transaction.atomic():
            # The team lock orders this after a concurrent removal of the
            # leader from the team (which clears the leader).
            team = _lock_team(slug, team_id)
            link = team and ProjectTeam.objects.filter(project_id=project_id, team=team).first()
            if not link:
                return Response(status=status.HTTP_404_NOT_FOUND)
            if leader_id and not active_team_members().filter(team=team, member_id=leader_id).exists():
                return Response({"leader_id": ["Must be a member of this team."]}, status=status.HTTP_400_BAD_REQUEST)
            ProjectTeam.objects.filter(pk=link.pk).update(
                leader_id=leader_id, updated_at=timezone.now(), updated_by=request.user
            )
            return Response(serialize_project_team(_links(slug, project_id).get(pk=link.pk)))

    @allow_permission([ROLE.ADMIN])
    def delete(self, request, slug, project_id, team_id):
        with transaction.atomic():
            project, team = _lock_project_and_team(slug, project_id, team_id)
            if not project or not team or not ProjectTeam.objects.filter(project=project, team=team).exists():
                return Response(status=status.HTTP_404_NOT_FOUND)
            # The team's members, plus anyone it added here who has left it since.
            user_ids = set(TeamMember.objects.filter(team=team).values_list("member_id", flat=True))
            user_ids |= set(
                ProjectMember.objects.filter(project=project, source_team=team, is_active=True).values_list(
                    "member_id", flat=True
                )
            )
            # Hard-deleted, the team's repository in this project with it. Its
            # routing rules here are kept, disabled.
            ProjectTeam.all_objects.filter(project=project, team=team).delete()
            ProjectTeamRepository.all_objects.filter(project=project, team=team).delete()
            ProjectRoutingRule.all_objects.filter(project=project, team=team).update(enabled=False)
            removed = sync_project_members([project.id], user_ids, actor=request.user, request=request)["removed"]
            kept = ProjectMember.objects.filter(project=project, member_id__in=user_ids, is_active=True).values_list(
                "member_id", flat=True
            )
            return Response(
                {
                    "removed_member_ids": sorted(str(member_id) for member_id in removed),
                    "kept_member_ids": sorted(str(member_id) for member_id in kept),
                }
            )
