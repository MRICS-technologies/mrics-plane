# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import models

# Module imports
from plane.db.models.project import ProjectBaseModel


class RepoProjectMapping(ProjectBaseModel):
    github_installation_id = models.BigIntegerField()
    github_repo = models.CharField(max_length=500)
    base_branch = models.CharField(max_length=255, default="dev")
    is_default = models.BooleanField(default=True)
    repo_label = models.CharField(max_length=255, blank=True)

    def __str__(self):
        """Return the repo mapping"""
        return f"{self.github_repo} <{self.project.name}>"

    class Meta:
        unique_together = ["project", "github_repo"]
        verbose_name = "Repo Project Mapping"
        verbose_name_plural = "Repo Project Mappings"
        db_table = "github_repo_mappings"
        ordering = ("-created_at",)


class IssueGitLink(ProjectBaseModel):
    KIND_CHOICES = (("branch", "Branch"), ("pr", "Pull Request"))
    STATE_CHOICES = (
        ("open", "Open"),
        ("merged", "Merged"),
        ("closed", "Closed"),
        ("unknown", "Unknown"),
    )
    DETECTED_VIA_CHOICES = (
        ("manual", "Manual"),
        ("branch", "Branch"),
        ("title", "Title"),
        ("commit", "Commit"),
    )

    issue = models.ForeignKey("db.Issue", related_name="git_links", on_delete=models.CASCADE)
    github_repo = models.CharField(max_length=500)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    ref = models.CharField(max_length=500)
    url = models.URLField()
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default="unknown")
    detected_via = models.CharField(max_length=20, choices=DETECTED_VIA_CHOICES, default="manual")

    def __str__(self):
        """Return the issue git link"""
        return f"{self.issue_id}-{self.github_repo}-{self.kind}-{self.ref}"

    class Meta:
        unique_together = ["issue", "github_repo", "kind", "ref"]
        verbose_name = "Issue Git Link"
        verbose_name_plural = "Issue Git Links"
        db_table = "issue_git_links"
        ordering = ("-created_at",)
