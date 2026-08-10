# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import re

# Third party imports
from rest_framework import serializers

# Module imports
from .base import BaseSerializer

from plane.db.models.integration.github_sync import RepoProjectMapping, IssueGitLink
from plane.db.models.integration.github_app import GithubAppInstallation, GithubEnabledRepository

# ---------------------------------------------------------------------------
# S2: Workspace Installation & Repository serializers
# ---------------------------------------------------------------------------


class GithubAppInstallationSerializer(BaseSerializer):
    installation_id = serializers.IntegerField()

    class Meta:
        model = GithubAppInstallation
        fields = [
            "id",
            "installation_id",
            "account_login",
            "account_type",
            "account_avatar_url",
            "repository_selection",
            "is_active",
            "suspended_at",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "account_avatar_url",
            "repository_selection",
            "is_active",
            "suspended_at",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]

    def validate_installation_id(self, value):
        if value <= 0:
            raise serializers.ValidationError("installation_id must be a positive integer.")
        return value

    def validate(self, attrs):
        workspace = self.context.get("workspace")
        if self.instance is None and workspace is not None:
            existing = GithubAppInstallation.objects.filter(workspace=workspace).exists()
            if existing:
                raise serializers.ValidationError(
                    {"installation_id": "This workspace already has an active installation."},
                    code="conflict",
                )
        return attrs


_FULL_NAME_RE = re.compile(r"^[^\s/]+/[^\s/]+$")


class GithubEnabledRepositorySerializer(BaseSerializer):
    class Meta:
        model = GithubEnabledRepository
        fields = [
            "id",
            "github_repository_id",
            "full_name",
            "is_enabled",
            "private",
            "default_branch",
            "html_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_github_repository_id(self, value):
        if value <= 0:
            raise serializers.ValidationError("github_repository_id must be a positive integer.")
        return value

    def validate_full_name(self, value):
        if not _FULL_NAME_RE.match(value):
            raise serializers.ValidationError(
                "full_name must be exactly 'owner/repository' (two non-blank, "
                "slash-separated segments with no whitespace).",
                code="invalid",
            )
        return value


class GithubEnabledRepositoryNestedSerializer(BaseSerializer):
    """Lightweight nested serializer for safe mapping-list responses."""

    class Meta:
        model = GithubEnabledRepository
        fields = ["id", "github_repository_id", "full_name", "is_enabled", "default_branch"]


# ---------------------------------------------------------------------------
# S2: Hardened RepoProjectMappingSerializer (explicit fields, no __all__)
# ---------------------------------------------------------------------------


class RepoProjectMappingSerializer(BaseSerializer):
    repository_detail = GithubEnabledRepositoryNestedSerializer(source="repository", read_only=True)
    repository_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = RepoProjectMapping
        fields = [
            "id",
            "github_repo",
            "base_branch",
            "is_default",
            "repo_label",
            "repository_id",
            "repository_detail",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "github_repo",
            "is_default",
            "created_at",
            "updated_at",
            "repository_detail",
        ]

    def validate_repository_id(self, value):
        if value is None:
            return value
        try:
            repo = GithubEnabledRepository.objects.select_related("installation").get(pk=value)
        except GithubEnabledRepository.DoesNotExist:
            raise serializers.ValidationError("Repository not found.", code="not_found")

        self._resolved_repo = repo
        return value

    def validate(self, attrs):
        repository_id = attrs.pop("repository_id", None)

        if repository_id is not None:
            repo = getattr(self, "_resolved_repo", None)
            if repo is None:
                raise serializers.ValidationError({"repository_id": "Repository not found."}, code="not_found")

            project = self.context.get("project")
            if project is not None:
                if repo.installation.workspace_id != project.workspace_id:
                    raise serializers.ValidationError(
                        {"repository_id": "Repository does not belong to this workspace."},
                        code="cross_workspace",
                    )
                if not repo.installation.is_active:
                    raise serializers.ValidationError(
                        {"repository_id": "The installation for this repository is not active."},
                        code="inactive_installation",
                    )
                if not repo.is_enabled:
                    raise serializers.ValidationError(
                        {"repository_id": "The repository is not enabled."},
                        code="disabled_repository",
                    )

            attrs["repository"] = repo
            attrs["github_installation_id"] = repo.installation.installation_id
            attrs["github_repo"] = repo.full_name

        if "github_repo" not in attrs:
            raise serializers.ValidationError(
                {"repository_id": "A repository_id is required to create a mapping."},
                code="required",
            )

        return attrs


class IssueGitLinkSerializer(BaseSerializer):
    class Meta:
        model = IssueGitLink
        fields = "__all__"
        read_only_fields = ["id", "workspace", "project", "issue", "created_at", "updated_at"]
