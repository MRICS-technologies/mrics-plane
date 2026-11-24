# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Prefetch
from django.utils import timezone

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers.team import TeamMembersSerializer, TeamWriteSerializer, serialize_team
from plane.db.models import ProjectTeamRepository, Team, TeamMember, Workspace, WorkspaceMember
from ..base import BaseAPIView

DUPLICATE_NAME = {"name": ["A team with this name already exists in this workspace."]}


def _teams(slug):
    # Members who left the workspace keep their row but are not listed.
    active_members = TeamMember.objects.filter(
        Exists(
            WorkspaceMember.objects.filter(
                workspace_id=OuterRef("workspace_id"), member_id=OuterRef("member_id"), is_active=True
            )
        )
    )
    return Team.objects.filter(workspace__slug=slug).prefetch_related(Prefetch("team_members", queryset=active_members))


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
        team = Team.objects.filter(workspace__slug=slug, pk=team_id).first()
        if not team:
            return Response(status=status.HTTP_404_NOT_FOUND)
        with transaction.atomic():
            # The team is soft-deleted (its name is freed) by a direct update:
            # Team.delete() would queue the soft-delete cascade. Updating first
            # locks the row, so a concurrent project team repository write
            # (which locks it too) either lands before and is deleted below,
            # or finds the team gone. Memberships are hard-deleted so the
            # members can join another team.
            now = timezone.now()
            Team.objects.filter(pk=team.pk).update(deleted_at=now, updated_at=now)
            TeamMember.all_objects.filter(team=team).delete()
            ProjectTeamRepository.all_objects.filter(team=team).delete()
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
            # One team per member: a member of another team is moved here
            # (last writer wins; update_or_create retries the lookup when a
            # concurrent insert hits the constraint). This and the TeamMember
            # (workspace, member) constraint are the only places that encode
            # the rule. Sorted so concurrent adds lock rows in the same order.
            for member_id in sorted(member_ids):
                TeamMember.objects.update_or_create(
                    workspace_id=team.workspace_id, member_id=member_id, defaults={"team": team}
                )
        return Response(serialize_team(_teams(slug).get(pk=team.pk)))


class WorkspaceTeamMemberDetailEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, team_id, member_id):
        # soft=False: the soft-deletion queryset's delete() is soft by default.
        deleted, _ = TeamMember.objects.filter(
            workspace__slug=slug, team_id=team_id, team__deleted_at__isnull=True, member_id=member_id
        ).delete(soft=False)
        if not deleted:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
