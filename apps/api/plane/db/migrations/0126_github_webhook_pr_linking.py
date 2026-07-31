# Additive foundation for P4 GitHub pull_request webhook processing.
#
# This migration only adds a new table and two nullable columns; it does not
# alter, drop, or backfill any existing column, table, or row. Every
# pre-existing `IssueGitLink` row (branch-kind links from S1) keeps working
# unchanged with `pr_number`/`github_updated_at` left null.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0125_github_workspace_installation_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="GithubWebhookDelivery",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Last Modified At")),
                ("deleted_at", models.DateTimeField(blank=True, null=True, verbose_name="Deleted At")),
                (
                    "id",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                ("delivery_id", models.CharField(max_length=255)),
                ("event", models.CharField(blank=True, max_length=100)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="githubwebhookdelivery_created_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Created By",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="githubwebhookdelivery_updated_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Last Modified By",
                    ),
                ),
            ],
            options={
                "verbose_name": "Github Webhook Delivery",
                "verbose_name_plural": "Github Webhook Deliveries",
                "db_table": "github_webhook_deliveries",
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddField(
            model_name="issuegitlink",
            name="pr_number",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="issuegitlink",
            name="github_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="githubwebhookdelivery",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=("delivery_id",),
                name="github_webhook_delivery_unique_delivery_id_when_deleted_at_null",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="issuegitlink",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="issuegitlink",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=("issue", "github_repo", "kind", "ref"),
                name="issuegitlink_unique_live_issue_repo_kind_ref",
            ),
        ),
        migrations.AddConstraint(
            model_name="issuegitlink",
            constraint=models.UniqueConstraint(
                condition=models.Q(("kind", "pr"), ("deleted_at__isnull", True)),
                fields=("workspace", "github_repo", "pr_number"),
                name="issuegitlink_unique_repo_pr_number_when_pr_and_deleted_at_null",
            ),
        ),
    ]
