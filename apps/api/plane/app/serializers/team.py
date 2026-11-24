# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import serializers


class TeamWriteSerializer(serializers.Serializer):
    """Create/update body."""

    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class TeamMembersSerializer(serializers.Serializer):
    member_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=500)


def serialize_team(team):
    """Read shape shared by every team endpoint; expects the members prefetched."""
    return {
        "id": str(team.id),
        "name": team.name,
        "description": team.description,
        "member_ids": [str(row.member_id) for row in team.team_members.all()],
        "created_at": team.created_at,
    }
