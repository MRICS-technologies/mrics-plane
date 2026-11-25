# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers.team import (
    TeamMembersSerializer,
    TeamWriteSerializer,
    active_team_members,
    serialize_team,
)
from plane.db.models import (
    ProjectMember,
    ProjectTeam,
    ProjectTeamRepository,
    Team,
    TeamMember,
    Workspace,
    WorkspaceMember,
)
from plane.services.teams.project_sync import locked_teams, sync_team_members
from ..base import BaseAPIView

DUPLICATE_NAME = {"name": ["A team with this name already exists in this workspace."]}


def _teams(slug):
    return Team.objects.filter(workspace__slug=slug).prefetch_related(
        Prefetch("team_members", queryset=active_team_members()),
        Prefetch("project_links", queryset=ProjectTeam.objects.filter(project__deleted_at__isnull=True)),
    )


class WorkspaceTeamEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def get(self, request, slug):
        return Response([serialize_team(team) for team in _teams(slug).order_by("name")])

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug):
        serializer = TeamWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workspace = Workspace.objects.get(slug=slug)
        data = serializer.validated_data
        try:
            with transaction.atomic():
                team = Team.objects.create(
                    workspace=workspace, name=data["name"], description=data.get("description", "")
                )
        except IntegrityError:
            return Response(DUPLICATE_NAME, status=status.HTTP_409_CONFLICT)
        return Response(serialize_team(_teams(slug).get(pk=team.pk)), status=status.HTTP_201_CREATED)


class WorkspaceTeamDetailEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def patch(self, request, slug, team_id):
        team = _teams(slug).filter(pk=team_id).first()
        if not team:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = TeamWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        for field, value in data.items():
            setattr(team, field, value)
        try:
            with transaction.atomic():
                team.save(update_fields=[*data, "updated_at"])
        except IntegrityError:
            return Response(DUPLICATE_NAME, status=status.HTTP_409_CONFLICT)
        return Response(serialize_team(_teams(slug).get(pk=team.pk)))

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, team_id):
        with transaction.atomic():
            # The team row lock makes a concurrent attach, member change or
            # project team repository write (which lock it too) either land
            # before and be undone below, or find the team gone.
            team = locked_teams(slug).filter(pk=team_id).first()
            if not team:
                return Response(status=status.HTTP_404_NOT_FOUND)
            # Its members, plus anyone it added to a project who has left it since.
            user_ids = set(TeamMember.objects.filter(team=team).values_list("member_id", flat=True))
            user_ids |= set(
                ProjectMember.objects.filter(source_team=team, is_active=True).values_list("member_id", flat=True)
            )
            # Soft-deleted (its name is freed) by a direct update: Team.delete()
            # would queue the soft-delete cascade. Memberships are hard-deleted
            # so the members can join another team; project links too.
            now = timezone.now()
            Team.objects.filter(pk=team.pk).update(deleted_at=now, updated_at=now)
            TeamMember.all_objects.filter(team=team).delete()
            ProjectTeamRepository.all_objects.filter(team=team).delete()
            ProjectTeam.all_objects.filter(team=team).delete()
            sync_team_members(team.workspace_id, user_ids, actor=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkspaceTeamMembersEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug, team_id):
        team = Team.objects.filter(workspace__slug=slug, pk=team_id).first()
        if not team:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = TeamMembersSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member_ids = set(serializer.validated_data["member_ids"])
        active = set(
            WorkspaceMember.objects.filter(
                workspace_id=team.workspace_id, member_id__in=member_ids, is_active=True
            ).values_list("member_id", flat=True)
        )
        invalid = member_ids - active
        if invalid:
            return Response({"member_ids": sorted(str(i) for i in invalid)}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Lock this team and the ones the members leave, in id order.
            old_team_ids = set(
                TeamMember.objects.filter(workspace_id=team.workspace_id, member_id__in=member_ids)
                .exclude(team=team)
                .values_list("team_id", flat=True)
            )
            if team not in locked_teams(slug).filter(pk__in={team.pk, *old_team_ids}):
                return Response(status=status.HTTP_404_NOT_FOUND)
            # One team per member: a member of another team is moved here
            # (last writer wins; update_or_create retries the lookup when a
            # concurrent insert hits the constraint). This and the TeamMember
            # (workspace, member) constraint are the only places that encode
            # the rule. Sorted so concurrent adds lock rows in the same order.
            for member_id in sorted(member_ids):
                TeamMember.objects.update_or_create(
                    workspace_id=team.workspace_id, member_id=member_id, defaults={"team": team}
                )
            # They lead no other team's projects now.
            ProjectTeam.objects.filter(workspace_id=team.workspace_id, leader_id__in=member_ids).exclude(
                team=team
            ).update(leader=None)
            sync_team_members(team.workspace_id, member_ids, team_id=team.pk, actor=request.user, request=request)
        return Response(serialize_team(_teams(slug).get(pk=team.pk)))


class WorkspaceTeamMemberDetailEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, team_id, member_id):
        with transaction.atomic():
            team = locked_teams(slug).filter(pk=team_id).first()
            # soft=False: the soft-deletion queryset's delete() is soft by default.
            deleted = team and TeamMember.objects.filter(team=team, member_id=member_id).delete(soft=False)[0]
            if not deleted:
                return Response(status=status.HTTP_404_NOT_FOUND)
            ProjectTeam.objects.filter(team=team, leader_id=member_id).update(leader=None)
            sync_team_members(team.workspace_id, [member_id], actor=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
