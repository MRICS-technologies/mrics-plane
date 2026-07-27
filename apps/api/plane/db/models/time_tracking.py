# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.conf import settings
from django.db import models

from .project import ProjectBaseModel


class WorkItemWorklog(ProjectBaseModel):
    class Source(models.TextChoices):
        TIMER = "timer", "Timer"
        MANUAL = "manual", "Manual"
        IMPORT = "import", "Import"

    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="worklogs")
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="work_item_worklogs",
    )
    date = models.DateField()
    duration = models.DecimalField(max_digits=12, decimal_places=4)
    description = models.TextField(blank=True, default="")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "work_item_worklogs"
        ordering = ("-date", "-created_at")


class ActiveTimer(ProjectBaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="active_work_item_timers",
    )
    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="active_timers")
    started_at = models.DateTimeField()
    last_warned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "active_work_item_timers"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(deleted_at__isnull=True),
                name="active_timer_unique_active_user",
            )
        ]
