# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import IntegrityError, transaction

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers.team import TeamMembersSerializer, TeamWriteSerializer, serialize_team
from plane.db.models import Team, TeamMember, Workspace, WorkspaceMember
from ..base import BaseAPIView

DUPLICATE_NAME = {"name": ["A team with this name already exists in this workspace."]}


def _teams(slug):
    return (
        Team.objects.filter(workspace__slug=slug).select_related("default_repository").prefetch_related("team_members")
    )


class WorkspaceTeamEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def get(self, request, slug):
        return Response([serialize_team(team) for team in _teams(slug).order_by("name")])

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug):
        serializer = TeamWriteSerializer(data=request.data, context={"workspace_slug": slug})
        serializer.is_valid(raise_exception=True)
        workspace = Workspace.objects.get(slug=slug)
        if Team.objects.filter(workspace=workspace, name=serializer.validated_data["name"]).exists():
            return Response(DUPLICATE_NAME, status=status.HTTP_409_CONFLICT)
        data = serializer.validated_data
        try:
            with transaction.atomic():
                team = Team.objects.create(
                    workspace=workspace,
                    name=data["name"],
                    description=data.get("description", ""),
                    default_repository_id=data.get("default_repository_id"),
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
        serializer = TeamWriteSerializer(data=request.data, partial=True, context={"workspace_slug": slug})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        name = data.get("name", team.name)
        if name != team.name and Team.objects.filter(workspace_id=team.workspace_id, name=name).exists():
            return Response(DUPLICATE_NAME, status=status.HTTP_409_CONFLICT)
        team.name = name
        team.description = data.get("description", team.description)
        if "default_repository_id" in data:
            team.default_repository_id = data["default_repository_id"]
        try:
            with transaction.atomic():
                team.save(update_fields=["name", "description", "default_repository", "updated_at"])
        except IntegrityError:
            return Response(DUPLICATE_NAME, status=status.HTTP_409_CONFLICT)
        return Response(serialize_team(_teams(slug).get(pk=team.pk)))

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, team_id):
        team = Team.objects.filter(workspace__slug=slug, pk=team_id).first()
        if not team:
            return Response(status=status.HTTP_404_NOT_FOUND)
        with transaction.atomic():
            # Memberships are hard-deleted so the members can join another
            # team; the team itself is soft-deleted (its name is freed).
            TeamMember.all_objects.filter(team=team).delete()
            team.delete()
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
            # One team per member: a member of another team is moved here.
            # This and the TeamMember (workspace, member) constraint are the
            # only places that encode the rule.
            rows = TeamMember.objects.select_for_update().filter(
                workspace_id=team.workspace_id, member_id__in=member_ids
            )
            existing = {row.member_id: row for row in rows}
            for member_id in member_ids:
                row = existing.get(member_id)
                if row is None:
                    TeamMember.objects.create(workspace_id=team.workspace_id, team=team, member_id=member_id)
                elif row.team_id != team.id:
                    row.team = team
                    row.save(update_fields=["team", "updated_at"])
        return Response(serialize_team(_teams(slug).get(pk=team.pk)))


class WorkspaceTeamMemberDetailEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, team_id, member_id):
        deleted, _ = TeamMember.all_objects.filter(
            workspace__slug=slug,
            team_id=team_id,
            team__deleted_at__isnull=True,
            member_id=member_id,
            deleted_at__isnull=True,
        ).delete()
        if not deleted:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
