# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import serializers

# Module imports
from plane.services.github.team_repo import usable_repositories


class TeamWriteSerializer(serializers.Serializer):
    """Create/update body. Needs ``workspace_slug`` in the context."""

    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    default_repository_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_default_repository_id(self, value):
        if value is not None and not usable_repositories(self.context["workspace_slug"]).filter(pk=value).exists():
            raise serializers.ValidationError("Must be an enabled repository of this workspace's GitHub installation.")
        return value


class TeamMembersSerializer(serializers.Serializer):
    member_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=500)


def serialize_team(team):
    """Read shape shared by every team endpoint; expects the members prefetched."""
    repository = team.default_repository
    return {
        "id": str(team.id),
        "name": team.name,
        "description": team.description,
        "default_repository": (
            {"id": str(repository.id), "full_name": repository.full_name}
            if repository and repository.deleted_at is None
            else None
        ),
        "member_ids": [str(row.member_id) for row in team.team_members.all()],
        "created_at": team.created_at,
    }
