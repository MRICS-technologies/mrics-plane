# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Module imports
from .base import BaseSerializer

from plane.db.models.integration.github_sync import RepoProjectMapping, IssueGitLink


class RepoProjectMappingSerializer(BaseSerializer):
    class Meta:
        model = RepoProjectMapping
        fields = "__all__"
        read_only_fields = ["id", "workspace", "project", "created_at", "updated_at"]


class IssueGitLinkSerializer(BaseSerializer):
    class Meta:
        model = IssueGitLink
        fields = "__all__"
        read_only_fields = ["id", "workspace", "project", "issue", "created_at", "updated_at"]
