# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import models
from django.db.models import Q

# Module imports
from plane.db.models import BaseModel


class GithubAppInstallation(BaseModel):
    """A verified GitHub App installation attached to a Plane workspace.

    ``installation_id`` is globally unique among live (non-soft-deleted)
    rows: GitHub itself only ever hands out one active installation per
    account, so a live row can attach that installation to exactly one
    workspace at a time. Soft-deleted rows are excluded so a disconnected
    installation can be reconnected (to the same or a different workspace)
    without colliding with its own history.
    """

    workspace = models.ForeignKey(
        "db.Workspace", on_delete=models.CASCADE, related_name="github_installations"
    )
    installation_id = models.BigIntegerField()
    account_login = models.CharField(max_length=255)
    account_type = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        """Return the installation account and workspace"""
        return f"{self.account_login} <{self.workspace.name}>"

    class Meta:
        verbose_name = "Github Installation"
        verbose_name_plural = "Github Installations"
        db_table = "github_installations"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["installation_id"],
                condition=Q(deleted_at__isnull=True),
                name="github_installation_unique_installation_id_when_deleted_at_null",
            )
        ]
        indexes = [
            models.Index(
                fields=["workspace"],
                condition=Q(deleted_at__isnull=True),
                name="github_install_ws_live_idx",
            )
        ]


class GithubEnabledRepository(BaseModel):
    """A GitHub repository enabled for use by a workspace's installation.

    ``github_repository_id`` is unique per installation among live rows: the
    same repository cannot be enabled twice under one installation, but the
    same GitHub repository id may reappear under a different (e.g.
    reconnected) installation.
    """

    installation = models.ForeignKey(
        "db.GithubAppInstallation", on_delete=models.CASCADE, related_name="enabled_repositories"
    )
    github_repository_id = models.BigIntegerField()
    full_name = models.CharField(max_length=500)
    is_enabled = models.BooleanField(default=True)

    def __str__(self):
        """Return the repository full name"""
        return self.full_name

    class Meta:
        verbose_name = "Github Enabled Repository"
        verbose_name_plural = "Github Enabled Repositories"
        db_table = "github_enabled_repositories"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["installation", "github_repository_id"],
                condition=Q(deleted_at__isnull=True),
                name="github_enabled_repo_unique_installation_repo_when_deleted_at_null",
            )
        ]
