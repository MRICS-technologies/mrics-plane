# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import models
from django.db.models import Q

# Module imports
from plane.db.models.base import BaseModel
from plane.db.models.project import ProjectBaseModel


class RepoProjectMapping(ProjectBaseModel):
    github_installation_id = models.BigIntegerField()
    github_repo = models.CharField(max_length=500)
    base_branch = models.CharField(max_length=255, default="dev")
    is_default = models.BooleanField(default=True)
    repo_label = models.CharField(max_length=255, blank=True)
    # Additive dynamic-mapping bridge: nullable so existing rows created
    # against the legacy github_installation_id/github_repo strings remain
    # valid untouched. Once the workspace installation flow lands, new rows
    # can populate this while old string fields stay authoritative until
    # every reader is migrated.
    repository = models.ForeignKey(
        "db.GithubEnabledRepository",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_mappings",
    )

    def __str__(self):
        """Return the repo mapping"""
        return f"{self.github_repo} <{self.project.name}>"

    class Meta:
        unique_together = ["project", "github_repo"]
        constraints = [
            # A project may keep any number of historical (soft-deleted)
            # mappings, but only one live mapping may be the default at a
            # time -- this never collapses existing rows, it only stops a
            # second live default from being created.
            models.UniqueConstraint(
                fields=["project"],
                condition=Q(is_default=True, deleted_at__isnull=True),
                name="repoprojectmapping_one_live_default_per_project",
            )
        ]
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
    # P4: nullable PR-correlation fields. Only populated for kind="pr" rows;
    # every pre-existing branch-kind row keeps working with these left null.
    pr_number = models.IntegerField(null=True, blank=True)
    github_updated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        """Return the issue git link"""
        return f"{self.issue_id}-{self.github_repo}-{self.kind}-{self.ref}"

    class Meta:
        constraints = [
            # Preserve the legacy live-row branch/link identity while allowing
            # a soft-deleted link to be recreated.
            models.UniqueConstraint(
                fields=["issue", "github_repo", "kind", "ref"],
                condition=Q(deleted_at__isnull=True),
                name="issuegitlink_unique_live_issue_repo_kind_ref",
            ),
            # A GitHub PR number is unique per issue inside a Plane workspace --
            # Phase 2 allows one PR to fan out to every issue sharing its
            # source branch, so the same (workspace, repo, pr_number) may now
            # back multiple live rows, one per linked issue.
            models.UniqueConstraint(
                fields=["workspace", "github_repo", "pr_number", "issue"],
                condition=Q(kind="pr", deleted_at__isnull=True),
                name="issuegitlink_unique_repo_pr_number_per_issue_when_pr_and_deleted_at_null",
            ),
        ]
        verbose_name = "Issue Git Link"
        verbose_name_plural = "Issue Git Links"
        db_table = "issue_git_links"
        ordering = ("-created_at",)


class GithubWebhookDelivery(BaseModel):
    """Dedup record for a processed GitHub webhook delivery.

    Only the delivery id and event name are stored -- never the raw payload
    or any secret -- so a duplicate `X-GitHub-Delivery` can be recognised and
    acknowledged with 200 without reprocessing.
    """

    delivery_id = models.CharField(max_length=255)
    event = models.CharField(max_length=100, blank=True)
    # 0129: for triage only -- the webhook resolves the workspace from the
    # installation row it looks up, never from this stored value.
    installation_id = models.BigIntegerField(null=True, blank=True)

    def __str__(self):
        """Return the delivery id and event"""
        return f"{self.delivery_id}-{self.event}"

    class Meta:
        verbose_name = "Github Webhook Delivery"
        verbose_name_plural = "Github Webhook Deliveries"
        db_table = "github_webhook_deliveries"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["delivery_id"],
                condition=Q(deleted_at__isnull=True),
                name="github_webhook_delivery_unique_delivery_id_when_deleted_at_null",
            )
        ]
