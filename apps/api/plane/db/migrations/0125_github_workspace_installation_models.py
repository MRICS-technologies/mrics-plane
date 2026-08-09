# Additive foundation for dynamic (per-workspace) GitHub App installations.
#
# This migration only adds new tables/columns/constraints; it does not
# replace, drop, or backfill any existing column, table, or row. The new
# `RepoProjectMapping.repository` FK is nullable and left unpopulated --
# existing mappings keep working off their legacy `github_installation_id`/
# `github_repo` string fields until a later slice migrates callers over, per
# the ratchet approach documented in the GitHub integration PRD (no network
# calls, no destructive rewrite of historical rows).
#
# The one exception is `dedupe_live_default_mappings` below: it flips
# `is_default` on rows, but never deletes or otherwise rewrites a mapping, and
# it runs before the new `repoprojectmapping_one_live_default_per_project`
# constraint so pre-existing data with more than one live default per project
# doesn't fail that AddConstraint.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def dedupe_live_default_mappings(apps, schema_editor):
    """Collapse any project with more than one live default mapping down to
    exactly one, so the unique constraint added right after this can apply
    cleanly. Deterministic: keeps the newest live default (by created_at,
    then id) and flips the rest to is_default=False. No row is deleted or
    otherwise rewritten.
    """
    RepoProjectMapping = apps.get_model("db", "RepoProjectMapping")

    duplicate_project_ids = (
        RepoProjectMapping.objects.filter(is_default=True, deleted_at__isnull=True)
        .values("project_id")
        .annotate(live_default_count=models.Count("id"))
        .filter(live_default_count__gt=1)
        .values_list("project_id", flat=True)
    )
    for project_id in duplicate_project_ids:
        live_defaults = RepoProjectMapping.objects.filter(
            project_id=project_id, is_default=True, deleted_at__isnull=True
        ).order_by("-created_at", "-id")
        for mapping in live_defaults[1:]:
            mapping.is_default = False
            mapping.save(update_fields=["is_default"])


def noop_reverse(apps, schema_editor):
    # ponytail: reversing can't recover which rows this flipped (that
    # information isn't retained), and leaving them as-is on unapply is not
    # destructive, so the reverse is a deliberate no-op.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0124_github_sync_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="GithubAppInstallation",
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
                ("installation_id", models.BigIntegerField()),
                ("account_login", models.CharField(max_length=255)),
                ("account_type", models.CharField(blank=True, max_length=50)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="githubappinstallation_created_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Created By",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="githubappinstallation_updated_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Last Modified By",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="github_installations",
                        to="db.workspace",
                    ),
                ),
            ],
            options={
                "verbose_name": "Github Installation",
                "verbose_name_plural": "Github Installations",
                "db_table": "github_installations",
                "ordering": ("-created_at",),
            },
        ),
        migrations.CreateModel(
            name="GithubEnabledRepository",
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
                ("github_repository_id", models.BigIntegerField()),
                ("full_name", models.CharField(max_length=500)),
                ("is_enabled", models.BooleanField(default=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="githubenabledrepository_created_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Created By",
                    ),
                ),
                (
                    "installation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="enabled_repositories",
                        to="db.githubappinstallation",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="githubenabledrepository_updated_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Last Modified By",
                    ),
                ),
            ],
            options={
                "verbose_name": "Github Enabled Repository",
                "verbose_name_plural": "Github Enabled Repositories",
                "db_table": "github_enabled_repositories",
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddField(
            model_name="repoprojectmapping",
            name="repository",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="project_mappings",
                to="db.githubenabledrepository",
            ),
        ),
        migrations.AddConstraint(
            model_name="githubappinstallation",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=("installation_id",),
                name="github_installation_unique_installation_id_when_deleted_at_null",
            ),
        ),
        migrations.AddIndex(
            model_name="githubappinstallation",
            index=models.Index(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=["workspace"],
                name="github_install_ws_live_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="githubenabledrepository",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=("installation", "github_repository_id"),
                name="github_enabled_repo_unique_installation_repo_when_deleted_at_null",
            ),
        ),
        migrations.RunPython(dedupe_live_default_mappings, noop_reverse),
        migrations.AddConstraint(
            model_name="repoprojectmapping",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_default", True), ("deleted_at__isnull", True)),
                fields=("project",),
                name="repoprojectmapping_one_live_default_per_project",
            ),
        ),
    ]
