# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db.models import Exists, OuterRef

# Third party imports
from rest_framework import serializers

# Module imports
from plane.db.models import TeamMember, WorkspaceMember


class TeamWriteSerializer(serializers.Serializer):
    """Create/update body."""

    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class TeamMembersSerializer(serializers.Serializer):
    member_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=500)


class ProjectTeamAttachSerializer(serializers.Serializer):
    team_id = serializers.UUIDField()


class ProjectTeamLeaderSerializer(serializers.Serializer):
    leader_id = serializers.UUIDField(allow_null=True)


def active_team_members():
    """Team memberships of active workspace members: members who left the
    workspace keep their row but are not listed."""
    return TeamMember.objects.filter(
        Exists(
            WorkspaceMember.objects.filter(
                workspace_id=OuterRef("workspace_id"), member_id=OuterRef("member_id"), is_active=True
            )
        )
    )


def serialize_team(team):
    """Read shape shared by every team endpoint; expects active_team_members()
    prefetched."""
    return {
        "id": str(team.id),
        "name": team.name,
        "description": team.description,
        "member_ids": [str(row.member_id) for row in team.team_members.all()],
        "created_at": team.created_at,
    }


def serialize_project_team(link):
    """A team attached to a project; expects the team and its
    active_team_members() prefetched. A leader who is no longer among them
    reads as no leader."""
    member_ids = [str(row.member_id) for row in link.team.team_members.all()]
    leader_id = str(link.leader_id) if link.leader_id else None
    return {
        "id": str(link.id),
        "team": {"id": str(link.team_id), "name": link.team.name, "member_ids": member_ids},
        "leader_id": leader_id if leader_id in member_ids else None,
        "created_at": link.created_at,
    }
