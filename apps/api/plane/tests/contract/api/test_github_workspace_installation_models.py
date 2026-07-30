# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for the S1 GitHub workspace installation foundation:

- `GithubAppInstallation` / `GithubEnabledRepository` partial-unique constraints
  (PostgreSQL-only `condition=` constraints, so these must run against a real
  Postgres, not SQLite/`--nomigrations` in-memory substitutes).
- `RepoProjectMapping` keeping historical rows while allowing only one live
  default mapping per project.
- The read-only P1 credentials bridge (`plane.services.github.credentials`).

None of these tests contact GitHub.
"""

import pytest
from unittest.mock import patch
from django.db import IntegrityError, transaction

from plane.db.models import Project
from plane.db.models.integration.github_app import GithubEnabledRepository, GithubAppInstallation
from plane.db.models.integration.github_sync import RepoProjectMapping
from plane.license.models import InstanceConfiguration
from plane.license.utils.encryption import encrypt_data
from plane.services.github.credentials import (
    DEFAULT_GITHUB_API_BASE_URL,
    DEFAULT_GITHUB_HTML_BASE_URL,
    get_github_app_credentials,
)


@pytest.fixture
def project(db, workspace, create_user):
    return Project.objects.create(
        name="Test Project",
        identifier="TP",
        workspace=workspace,
        created_by=create_user,
    )


@pytest.fixture
def installation(db, workspace):
    return GithubAppInstallation.objects.create(
        workspace=workspace, installation_id=42, account_login="acme", account_type="Organization"
    )


@pytest.mark.contract
class TestGithubAppInstallationConstraints:
    @pytest.mark.django_db
    def test_installation_id_unique_among_live_rows(self, workspace, installation):
        with transaction.atomic(), pytest.raises(IntegrityError):
            GithubAppInstallation.objects.create(
                workspace=workspace, installation_id=installation.installation_id, account_login="other"
            )

    @pytest.mark.django_db
    def test_soft_deleted_installation_frees_installation_id_for_reuse(self, workspace, installation):
        with patch("plane.db.mixins.soft_delete_related_objects.delay"):
            installation.delete()  # soft delete: sets deleted_at, does not remove the row

        recreated = GithubAppInstallation.objects.create(
            workspace=workspace, installation_id=installation.installation_id, account_login="acme-reconnected"
        )

        assert recreated.pk != installation.pk
        assert GithubAppInstallation.all_objects.filter(installation_id=installation.installation_id).count() == 2


@pytest.mark.contract
class TestGithubEnabledRepositoryConstraints:
    @pytest.mark.django_db
    def test_repository_unique_per_installation_among_live_rows(self, installation):
        GithubEnabledRepository.objects.create(
            installation=installation, github_repository_id=1, full_name="acme/widgets"
        )

        with transaction.atomic(), pytest.raises(IntegrityError):
            GithubEnabledRepository.objects.create(
                installation=installation, github_repository_id=1, full_name="acme/widgets-renamed"
            )

    @pytest.mark.django_db
    def test_same_repository_id_allowed_under_different_installation(self, workspace, installation):
        other_installation = GithubAppInstallation.objects.create(
            workspace=workspace, installation_id=installation.installation_id + 1, account_login="other-org"
        )
        GithubEnabledRepository.objects.create(
            installation=installation, github_repository_id=7, full_name="acme/widgets"
        )

        # Should not raise: different installation, same github_repository_id.
        GithubEnabledRepository.objects.create(
            installation=other_installation, github_repository_id=7, full_name="acme/widgets"
        )


@pytest.mark.contract
class TestRepoProjectMappingDefaultConstraint:
    @pytest.mark.django_db
    def test_only_one_live_default_mapping_per_project(self, project):
        RepoProjectMapping.objects.create(
            project=project, github_installation_id=1, github_repo="acme/widgets", is_default=True
        )

        with transaction.atomic(), pytest.raises(IntegrityError):
            RepoProjectMapping.objects.create(
                project=project, github_installation_id=1, github_repo="acme/gadgets", is_default=True
            )

    @pytest.mark.django_db
    def test_historical_non_default_mappings_are_preserved(self, project):
        first = RepoProjectMapping.objects.create(
            project=project, github_installation_id=1, github_repo="acme/widgets", is_default=True
        )
        # Retiring the old default (soft delete) preserves history and frees
        # up the "one live default" slot for a new mapping -- it does not
        # collapse/overwrite the retired row.
        with patch("plane.db.mixins.soft_delete_related_objects.delay"):
            first.delete()

        second = RepoProjectMapping.objects.create(
            project=project, github_installation_id=2, github_repo="acme/gadgets", is_default=True
        )

        assert RepoProjectMapping.all_objects.filter(project=project).count() == 2
        assert RepoProjectMapping.objects.filter(project=project).get() == second

    @pytest.mark.django_db
    def test_non_default_mapping_alongside_existing_default_is_allowed(self, project):
        RepoProjectMapping.objects.create(
            project=project, github_installation_id=1, github_repo="acme/widgets", is_default=True
        )

        # Not the default -> does not compete for the single-default slot.
        RepoProjectMapping.objects.create(
            project=project, github_installation_id=1, github_repo="acme/gadgets", is_default=False
        )

        assert RepoProjectMapping.objects.filter(project=project).count() == 2


@pytest.mark.contract
class TestGitHubAppCredentialsBridge:
    @pytest.mark.django_db
    def test_absent_configuration_returns_falsy_defaults(self):
        credentials = get_github_app_credentials()

        assert not credentials
        assert credentials.app_id == ""
        assert credentials.private_key == ""
        assert credentials.webhook_secret == ""
        assert credentials.github_base_url == DEFAULT_GITHUB_API_BASE_URL
        assert credentials.html_base_url == DEFAULT_GITHUB_HTML_BASE_URL
        assert credentials.enabled is False

    @pytest.mark.django_db
    def test_undecryptable_secret_falls_back_to_empty_string(self):
        InstanceConfiguration.objects.create(
            key="GITHUB_APP_ID", value="123456", category="GITHUB_APP", is_encrypted=False
        )
        InstanceConfiguration.objects.create(
            key="GITHUB_APP_PRIVATE_KEY",
            value="not-valid-ciphertext",
            category="GITHUB_APP",
            is_encrypted=True,
        )

        credentials = get_github_app_credentials()

        assert credentials.app_id == "123456"
        assert credentials.private_key == ""
        assert not credentials  # a broken private key still means "not usable"

    @pytest.mark.django_db
    def test_decrypts_encrypted_values_and_reports_configured_defaults(self):
        InstanceConfiguration.objects.create(
            key="GITHUB_APP_ID", value="123456", category="GITHUB_APP", is_encrypted=False
        )
        InstanceConfiguration.objects.create(
            key="GITHUB_APP_PRIVATE_KEY",
            value=encrypt_data("fake-pem-private-key"),
            category="GITHUB_APP",
            is_encrypted=True,
        )
        InstanceConfiguration.objects.create(
            key="GITHUB_APP_WEBHOOK_SECRET",
            value=encrypt_data("wh-secret"),
            category="GITHUB_APP",
            is_encrypted=True,
        )
        InstanceConfiguration.objects.create(
            key="GITHUB_APP_ENABLED", value="1", category="GITHUB_APP", is_encrypted=False
        )

        credentials = get_github_app_credentials()

        assert credentials
        assert credentials.app_id == "123456"
        assert credentials.private_key == "fake-pem-private-key"
        assert credentials.webhook_secret == "wh-secret"
        assert credentials.enabled is True
        # Base URLs default when not explicitly configured.
        assert credentials.github_base_url == DEFAULT_GITHUB_API_BASE_URL
        assert credentials.html_base_url == DEFAULT_GITHUB_HTML_BASE_URL

    @pytest.mark.django_db
    def test_custom_base_urls_override_defaults(self):
        InstanceConfiguration.objects.create(
            key="GITHUB_APP_GITHUB_BASE_URL",
            value="https://ghe.example.com/api/v3",
            category="GITHUB_APP",
        )
        InstanceConfiguration.objects.create(
            key="GITHUB_APP_HTML_BASE_URL",
            value="https://ghe.example.com",
            category="GITHUB_APP",
        )

        credentials = get_github_app_credentials()

        assert credentials.github_base_url == "https://ghe.example.com/api/v3"
        assert credentials.html_base_url == "https://ghe.example.com"

    @pytest.mark.django_db
    def test_repr_never_discloses_secret_fields(self):
        InstanceConfiguration.objects.create(
            key="GITHUB_APP_PRIVATE_KEY",
            value=encrypt_data("super-secret-pem"),
            category="GITHUB_APP",
            is_encrypted=True,
        )
        InstanceConfiguration.objects.create(
            key="GITHUB_APP_WEBHOOK_SECRET",
            value=encrypt_data("super-secret-webhook"),
            category="GITHUB_APP",
            is_encrypted=True,
        )
        InstanceConfiguration.objects.create(
            key="GITHUB_APP_CLIENT_SECRET",
            value=encrypt_data("super-secret-oauth"),
            category="GITHUB_APP",
            is_encrypted=True,
        )

        credentials = get_github_app_credentials()

        assert "super-secret-pem" not in repr(credentials)
        assert "super-secret-webhook" not in repr(credentials)
        assert "super-secret-oauth" not in repr(credentials)


@pytest.mark.contract
class TestDedupeLiveDefaultMappingsMigration:
    @pytest.mark.django_db
    def test_dedupe_keeps_newest_live_default_and_flips_the_rest(self, project):
        # Exercises the 0125 data migration's `dedupe_live_default_mappings`
        # directly: temporarily drop the partial-unique index it runs ahead
        # of (both live in the same migration -- see 0125's operations list),
        # seed two live defaults on one project, run the function, and check
        # exactly one deterministic default survives. The DROP INDEX is never
        # re-created here -- Django's transactional test rollback restores the
        # original index automatically.
        import importlib
        from datetime import timedelta

        from django.apps import apps as global_apps
        from django.db import connection
        from django.utils import timezone

        migration = importlib.import_module("plane.db.migrations.0125_github_workspace_installation_models")

        with connection.cursor() as cursor:
            cursor.execute("DROP INDEX IF EXISTS repoprojectmapping_one_live_default_per_project")

        older = RepoProjectMapping.objects.create(
            project=project, github_installation_id=1, github_repo="acme/widgets", is_default=True
        )
        RepoProjectMapping.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(days=1))
        newer = RepoProjectMapping.objects.create(
            project=project, github_installation_id=2, github_repo="acme/gadgets", is_default=True
        )

        migration.dedupe_live_default_mappings(global_apps, schema_editor=None)

        older.refresh_from_db()
        newer.refresh_from_db()
        assert older.is_default is False
        assert newer.is_default is True
        # Both rows are retained -- deduping never deletes or rewrites a mapping.
        assert RepoProjectMapping.all_objects.filter(project=project).count() == 2
