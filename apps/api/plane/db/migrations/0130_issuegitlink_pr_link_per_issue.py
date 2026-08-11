# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0129_github_discovery_fields"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="issuegitlink",
            name="issuegitlink_unique_repo_pr_number_when_pr_and_deleted_at_null",
        ),
        migrations.AddConstraint(
            model_name="issuegitlink",
            constraint=models.UniqueConstraint(
                fields=("workspace", "github_repo", "pr_number", "issue"),
                condition=Q(kind="pr", deleted_at__isnull=True),
                name="issuegitlink_unique_repo_pr_per_issue_when_pr_and_deleted_null",
            ),
        ),
    ]
