# Generated for GitHub Sync integration (Phase 3)

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0123_workitemworklog_auto_state_source"),
    ]

    operations = [
        migrations.CreateModel(
            name="RepoProjectMapping",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Last Modified At")),
                ("deleted_at", models.DateTimeField(blank=True, null=True, verbose_name="Deleted At")),
                ("id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ("github_installation_id", models.BigIntegerField()),
                ("github_repo", models.CharField(max_length=500)),
                ("base_branch", models.CharField(default="dev", max_length=255)),
                ("is_default", models.BooleanField(default=True)),
                ("repo_label", models.CharField(blank=True, max_length=255)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="repoprojectmapping_created_by", to=settings.AUTH_USER_MODEL, verbose_name="Created By")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="project_%(class)s", to="db.project")),
                ("updated_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="repoprojectmapping_updated_by", to=settings.AUTH_USER_MODEL, verbose_name="Last Modified By")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="workspace_%(class)s", to="db.workspace")),
            ],
            options={
                "verbose_name": "Repo Project Mapping",
                "verbose_name_plural": "Repo Project Mappings",
                "db_table": "github_repo_mappings",
                "ordering": ("-created_at",),
            },
        ),
        migrations.CreateModel(
            name="IssueGitLink",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Last Modified At")),
                ("deleted_at", models.DateTimeField(blank=True, null=True, verbose_name="Deleted At")),
                ("id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ("github_repo", models.CharField(max_length=500)),
                ("kind", models.CharField(choices=[("branch", "Branch"), ("pr", "Pull Request")], max_length=20)),
                ("ref", models.CharField(max_length=500)),
                ("url", models.URLField()),
                ("state", models.CharField(choices=[("open", "Open"), ("merged", "Merged"), ("closed", "Closed"), ("unknown", "Unknown")], default="unknown", max_length=20)),
                ("detected_via", models.CharField(choices=[("manual", "Manual"), ("branch", "Branch"), ("title", "Title"), ("commit", "Commit")], default="manual", max_length=20)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="issuegitlink_created_by", to=settings.AUTH_USER_MODEL, verbose_name="Created By")),
                ("issue", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="git_links", to="db.issue")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="project_%(class)s", to="db.project")),
                ("updated_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="issuegitlink_updated_by", to=settings.AUTH_USER_MODEL, verbose_name="Last Modified By")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="workspace_%(class)s", to="db.workspace")),
            ],
            options={
                "verbose_name": "Issue Git Link",
                "verbose_name_plural": "Issue Git Links",
                "db_table": "issue_git_links",
                "ordering": ("-created_at",),
            },
        ),
        migrations.AlterUniqueTogether(
            name="repoprojectmapping",
            unique_together={("project", "github_repo")},
        ),
        migrations.AlterUniqueTogether(
            name="issuegitlink",
            unique_together={("issue", "github_repo", "kind", "ref")},
        ),
    ]
