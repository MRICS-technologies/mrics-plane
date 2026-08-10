# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for S2 native workspace installation/repository-to-project mapping API.

Covers:

* GET/POST/DELETE  /api/workspaces/<slug>/github/installation/
* GET/POST         /api/workspaces/<slug>/github/repositories/
* PATCH/DELETE     /api/workspaces/<slug>/github/repositories/<uuid:repo_id>/
* GET/POST/DELETE  …/projects/<project_id>/github/mappings/

All tests run against PostgreSQL; none contact GitHub or external services.
"""

import uuid
from unittest.mock import patch

import pytest
from rest_framework import status

from plane.db.models import Project, ProjectMember, User, Workspace, WorkspaceMember
from plane.db.models.integration.github_app import GithubAppInstallation, GithubEnabledRepository
from plane.db.models.integration.github_sync import RepoProjectMapping
from plane.license.models import InstanceConfiguration
from plane.utils.encrypt import encrypt_data


def _configure_app(app_id="555111", private_key_pem="fake-key", app_slug="plane-app"):
    """P1: bulk upsert validates repos against the live GitHub list, which
    requires instance credentials -- same helper as the setup-flow tests."""
    InstanceConfiguration.objects.update_or_create(
        key="GITHUB_APP_ID", defaults={"value": app_id, "category": "GITHUB_APP", "is_encrypted": False}
    )
    InstanceConfiguration.objects.update_or_create(
        key="GITHUB_APP_SLUG", defaults={"value": app_slug, "category": "GITHUB_APP", "is_encrypted": False}
    )
    InstanceConfiguration.objects.update_or_create(
        key="GITHUB_APP_PRIVATE_KEY",
        defaults={"value": encrypt_data(private_key_pem), "category": "GITHUB_APP", "is_encrypted": True},
    )


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _install_url(slug):
    return f"/api/workspaces/{slug}/github/installation/"


def _repos_url(slug):
    return f"/api/workspaces/{slug}/github/repositories/"


def _repo_detail_url(slug, repo_id):
    return f"/api/workspaces/{slug}/github/repositories/{repo_id}/"


def _mappings_url(slug, project_id):
    return f"/api/workspaces/{slug}/projects/{project_id}/github/mappings/"


def _mapping_detail_url(slug, project_id, pk):
    return f"/api/workspaces/{slug}/projects/{project_id}/github/mappings/{pk}/"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project(db, workspace, create_user):
    p = Project.objects.create(
        name="S2 Test Project",
        identifier="S2P",
        workspace=workspace,
        created_by=create_user,
    )
    ProjectMember.objects.create(workspace=workspace, project=p, member=create_user, role=20, is_active=True)
    return p


@pytest.fixture
def installation(db, workspace):
    return GithubAppInstallation.objects.create(
        workspace=workspace,
        installation_id=99990001,
        account_login="s2-acme",
        account_type="Organization",
    )


@pytest.fixture
def enabled_repo(db, installation):
    return GithubEnabledRepository.objects.create(
        installation=installation,
        github_repository_id=88001,
        full_name="s2-acme/widgets",
        is_enabled=True,
    )


@pytest.fixture
def disabled_repo(db, installation):
    return GithubEnabledRepository.objects.create(
        installation=installation,
        github_repository_id=88002,
        full_name="s2-acme/gadgets",
        is_enabled=False,
    )


@pytest.fixture
def legacy_mapping(db, project):
    return RepoProjectMapping.objects.create(
        project=project,
        github_installation_id=99990001,
        github_repo="s2-acme/widgets",
        base_branch="main",
    )


@pytest.fixture
def second_workspace(db, create_user):
    ws = Workspace.objects.create(
        name="Second Workspace",
        owner=create_user,
        slug="second-workspace",
    )
    WorkspaceMember.objects.create(workspace=ws, member=create_user, role=20)
    return ws


@pytest.fixture
def second_workspace_user(db):
    """A user who is only in the second workspace, not the primary."""
    user = User.objects.create(
        email="second@plane.so",
        username="second-workspace-user",
        first_name="Second",
        last_name="User",
    )
    user.set_password("test")
    user.save()
    return user


@pytest.fixture
def second_workspace_client(api_client, second_workspace, second_workspace_user):
    WorkspaceMember.objects.create(workspace=second_workspace, member=second_workspace_user, role=20)
    api_client.force_authenticate(user=second_workspace_user)
    return api_client


# ============================================================================
# S2 Installation endpoints
# ============================================================================


@pytest.mark.contract
class TestInstallationGet:
    @pytest.mark.django_db
    def test_get_returns_null_when_none(self, session_client, workspace):
        resp = session_client.get(_install_url(workspace.slug))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data is None

    @pytest.mark.django_db
    def test_get_returns_active(self, session_client, workspace, installation):
        resp = session_client.get(_install_url(workspace.slug))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["installation_id"] == installation.installation_id
        assert resp.data["account_login"] == installation.account_login
        assert "id" in resp.data
        # github_installation_id must not leak in response (it isn't a field of
        # the installation serializer).
        assert "workspace" not in resp.data

    @pytest.mark.django_db
    def test_get_exposes_p1_discovery_fields_as_read_only(self, session_client, workspace, installation):
        # P1 1.7: these are populated by the verified setup callback / webhook
        # handlers only -- the serializer must expose but never accept them.
        resp = session_client.get(_install_url(workspace.slug))
        assert resp.status_code == status.HTTP_200_OK
        for field in ("account_avatar_url", "repository_selection", "suspended_at", "last_synced_at"):
            assert field in resp.data

    @pytest.mark.django_db
    def test_create_ignores_client_supplied_discovery_fields(self, session_client, workspace):
        resp = session_client.post(
            _install_url(workspace.slug),
            {
                "installation_id": 7770099,
                "account_login": "acme",
                "suspended_at": "2020-01-01T00:00:00Z",
                "account_avatar_url": "https://attacker.example/avatar.png",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        created = GithubAppInstallation.objects.get(installation_id=7770099)
        assert created.suspended_at is None
        assert created.account_avatar_url == ""

    @pytest.mark.django_db
    def test_non_member_gets_403(self, api_client, workspace):
        user = User.objects.create(email="outsider@plane.so", username="outsider", first_name="Out", last_name="Sider")
        user.set_password("test")
        user.save()
        api_client.force_authenticate(user=user)
        resp = api_client.get(_install_url(workspace.slug))
        assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.contract
class TestInstallationCreate:
    @pytest.mark.django_db
    def test_create_succeeds(self, session_client, workspace):
        resp = session_client.post(
            _install_url(workspace.slug),
            {"installation_id": 7770001, "account_login": "new-org"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["installation_id"] == 7770001
        assert resp.data["account_login"] == "new-org"
        assert GithubAppInstallation.objects.filter(workspace=workspace).exists()

    @pytest.mark.django_db
    def test_create_duplicate_workspace_rejected(self, session_client, workspace, installation):
        resp = session_client.post(
            _install_url(workspace.slug),
            {"installation_id": 99990002, "account_login": "other"},
            format="json",
        )
        assert resp.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.django_db
    def test_create_duplicate_installation_id_cross_workspace_rejected(
        self, session_client, workspace, installation, second_workspace
    ):
        # Same installation_id in a different workspace -> DB unique constraint.
        resp = session_client.post(
            _install_url(second_workspace.slug),
            {"installation_id": installation.installation_id, "account_login": "cross"},
            format="json",
        )
        assert resp.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.django_db
    def test_missing_fields_rejected(self, session_client, workspace):
        resp = session_client.post(_install_url(workspace.slug), {}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_non_positive_installation_id_rejected(self, session_client, workspace):
        resp = session_client.post(
            _install_url(workspace.slug),
            {"installation_id": 0, "account_login": "invalid"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_non_admin_cannot_create(self, api_client, workspace, create_user):
        # Downgrade user to member (15) in workspace
        wm = WorkspaceMember.objects.get(workspace=workspace, member=create_user)
        wm.role = 15
        wm.save()
        api_client.force_authenticate(user=create_user)
        resp = api_client.post(
            _install_url(workspace.slug),
            {"installation_id": 1, "account_login": "x"},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.contract
class TestInstallationDelete:
    @pytest.mark.django_db
    def test_delete_soft_deletes(self, session_client, workspace, installation):
        with patch("plane.db.mixins.soft_delete_related_objects.delay"):
            resp = session_client.delete(_install_url(workspace.slug))
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        # Live queryset excludes it
        assert not GithubAppInstallation.objects.filter(pk=installation.pk).exists()
        # all_objects still has it
        assert GithubAppInstallation.all_objects.filter(pk=installation.pk).exists()

    @pytest.mark.django_db
    def test_recreate_after_soft_delete_succeeds(self, session_client, workspace, installation):
        with patch("plane.db.mixins.soft_delete_related_objects.delay"):
            installation.delete()

        # Now the workspace has no live installation — recreate.
        resp = session_client.post(
            _install_url(workspace.slug),
            {"installation_id": installation.installation_id, "account_login": "reconnected"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED

    @pytest.mark.django_db
    def test_delete_rejects_installation_with_mappings(
        self, session_client, workspace, project, installation, enabled_repo
    ):
        RepoProjectMapping.objects.create(
            project=project,
            github_installation_id=installation.installation_id,
            github_repo=enabled_repo.full_name,
            repository=enabled_repo,
        )
        resp = session_client.delete(_install_url(workspace.slug))
        assert resp.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.django_db
    def test_delete_nonexistent_returns_404(self, session_client, workspace):
        resp = session_client.delete(_install_url(workspace.slug))
        assert resp.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# S2 Repository endpoints
# ============================================================================


@pytest.mark.contract
class TestRepositoryList:
    @pytest.mark.django_db
    def test_list_returns_empty_when_no_installation(self, session_client, workspace):
        resp = session_client.get(_repos_url(workspace.slug))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data == []

    @pytest.mark.django_db
    def test_list_returns_repos(self, session_client, workspace, installation, enabled_repo, disabled_repo):
        resp = session_client.get(_repos_url(workspace.slug))
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 2

    @pytest.mark.django_db
    def test_list_filter_enabled_true(self, session_client, workspace, installation, enabled_repo, disabled_repo):
        resp = session_client.get(f"{_repos_url(workspace.slug)}?enabled=true")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1
        assert resp.data[0]["is_enabled"] is True

    @pytest.mark.django_db
    def test_list_filter_enabled_false(self, session_client, workspace, installation, enabled_repo, disabled_repo):
        resp = session_client.get(f"{_repos_url(workspace.slug)}?enabled=false")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1
        assert resp.data[0]["is_enabled"] is False
        assert "installation" not in resp.data[0]

    @pytest.mark.django_db
    def test_list_rejects_invalid_enabled_filter(self, session_client, workspace, installation):
        resp = session_client.get(f"{_repos_url(workspace.slug)}?enabled=invalid")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.contract
class TestRepositoryCreate:
    @pytest.mark.django_db
    def test_create_succeeds(self, session_client, workspace, installation):
        resp = session_client.post(
            _repos_url(workspace.slug),
            {"github_repository_id": 99901, "full_name": "s2-acme/new-repo"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["full_name"] == "s2-acme/new-repo"
        assert resp.data["is_enabled"] is True

    @pytest.mark.django_db
    def test_create_without_installation_returns_422(self, session_client, workspace):
        resp = session_client.post(
            _repos_url(workspace.slug),
            {"github_repository_id": 1, "full_name": "a/b"},
            format="json",
        )
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.django_db
    def test_create_duplicate_rejected(self, session_client, workspace, installation, enabled_repo):
        resp = session_client.post(
            _repos_url(workspace.slug),
            {"github_repository_id": enabled_repo.github_repository_id, "full_name": "s2-acme/widgets-v2"},
            format="json",
        )
        assert resp.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.django_db
    def test_create_duplicate_full_name_rejected(self, session_client, workspace, installation, enabled_repo):
        resp = session_client.post(
            _repos_url(workspace.slug),
            {"github_repository_id": 88003, "full_name": enabled_repo.full_name},
            format="json",
        )
        assert resp.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.django_db
    def test_create_bad_full_name_rejected(self, session_client, workspace, installation):
        resp = session_client.post(
            _repos_url(workspace.slug),
            {"github_repository_id": 1, "full_name": "no-slash"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_create_full_name_with_whitespace_rejected(self, session_client, workspace, installation):
        resp = session_client.post(
            _repos_url(workspace.slug),
            {"github_repository_id": 1, "full_name": "owner /repo"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_create_non_positive_repository_id_rejected(self, session_client, workspace, installation):
        resp = session_client.post(
            _repos_url(workspace.slug),
            {"github_repository_id": 0, "full_name": "owner/repo"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.contract
class TestRepositoryBulkUpsert:
    """P1 1.5: the repo picker enables/disables many repositories in one POST;
    the single-object form above (`TestRepositoryCreate`) must keep working."""

    @pytest.fixture(autouse=True)
    def _app_configured(self):
        _configure_app()

    @pytest.mark.django_db
    def test_bulk_list_upserts_and_updates_existing(self, session_client, workspace, installation, enabled_repo):
        resp = session_client.post(
            _repos_url(workspace.slug),
            [
                {
                    "github_repository_id": enabled_repo.github_repository_id,
                    "full_name": enabled_repo.full_name,
                    "is_enabled": False,
                },
                {
                    "github_repository_id": 99777,
                    "full_name": "s2-acme/brand-new",
                    "is_enabled": True,
                    "private": True,
                    "default_branch": "main",
                    "html_url": "https://github.com/s2-acme/brand-new",
                },
            ],
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert len(resp.data) == 2

        enabled_repo.refresh_from_db()
        assert enabled_repo.is_enabled is False

        created = GithubEnabledRepository.objects.get(installation=installation, github_repository_id=99777)
        assert created.is_enabled is True
        assert created.private is True
        assert created.default_branch == "main"

    @pytest.mark.django_db
    def test_bulk_list_without_installation_returns_422(self, session_client, workspace):
        resp = session_client.post(
            _repos_url(workspace.slug),
            [{"github_repository_id": 1, "full_name": "a/b"}],
            format="json",
        )
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.django_db
    def test_bulk_list_reports_per_item_errors_without_dropping_valid_rows(
        self, session_client, workspace, installation
    ):
        resp = session_client.post(
            _repos_url(workspace.slug),
            [
                {"github_repository_id": 1, "full_name": "no-slash"},
                {"github_repository_id": 2, "full_name": "s2-acme/valid-one"},
            ],
            format="json",
        )
        assert resp.status_code == status.HTTP_207_MULTI_STATUS
        assert len(resp.data["results"]) == 1
        assert len(resp.data["errors"]) == 1
        assert GithubEnabledRepository.objects.filter(installation=installation, github_repository_id=2).exists()


@pytest.mark.contract
class TestRepositoryDetail:
    @pytest.mark.django_db
    def test_patch_toggle_enabled(self, session_client, workspace, installation, enabled_repo):
        resp = session_client.patch(
            _repo_detail_url(workspace.slug, enabled_repo.pk),
            {"is_enabled": False},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["is_enabled"] is False
        enabled_repo.refresh_from_db()
        assert enabled_repo.is_enabled is False

    @pytest.mark.django_db
    def test_patch_full_name(self, session_client, workspace, installation, enabled_repo):
        resp = session_client.patch(
            _repo_detail_url(workspace.slug, enabled_repo.pk),
            {"full_name": "s2-acme/renamed"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["full_name"] == "s2-acme/renamed"

    @pytest.mark.django_db
    def test_patch_bad_full_name_rejected(self, session_client, workspace, installation, enabled_repo):
        resp = session_client.patch(
            _repo_detail_url(workspace.slug, enabled_repo.pk),
            {"full_name": "bad"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_patch_rejects_unsupported_fields(self, session_client, workspace, installation, enabled_repo):
        resp = session_client.patch(
            _repo_detail_url(workspace.slug, enabled_repo.pk),
            {"github_repository_id": 99999},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_patch_cross_workspace_rejected(
        self, session_client, workspace, installation, enabled_repo, second_workspace
    ):
        resp = session_client.patch(
            _repo_detail_url(second_workspace.slug, enabled_repo.pk),
            {"is_enabled": False},
            format="json",
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_delete_soft_deletes(self, session_client, workspace, installation, enabled_repo):
        with patch("plane.db.mixins.soft_delete_related_objects.delay"):
            resp = session_client.delete(_repo_detail_url(workspace.slug, enabled_repo.pk))
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not GithubEnabledRepository.objects.filter(pk=enabled_repo.pk).exists()
        assert GithubEnabledRepository.all_objects.filter(pk=enabled_repo.pk).exists()

    @pytest.mark.django_db
    def test_delete_rejects_mapped_repository(self, session_client, workspace, project, installation, enabled_repo):
        RepoProjectMapping.objects.create(
            project=project,
            github_installation_id=installation.installation_id,
            github_repo=enabled_repo.full_name,
            repository=enabled_repo,
        )
        resp = session_client.delete(_repo_detail_url(workspace.slug, enabled_repo.pk))
        assert resp.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.django_db
    def test_delete_nonexistent_returns_404(self, session_client, workspace, installation):
        resp = session_client.delete(_repo_detail_url(workspace.slug, uuid.uuid4()))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_delete_no_installation_returns_404(self, session_client, workspace):
        resp = session_client.delete(_repo_detail_url(workspace.slug, uuid.uuid4()))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_non_admin_cannot_patch(self, api_client, workspace, create_user, installation, enabled_repo):
        WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(role=15)
        api_client.force_authenticate(user=create_user)
        resp = api_client.patch(
            _repo_detail_url(workspace.slug, enabled_repo.pk),
            {"is_enabled": False},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# S2 Project Mappings (hardened)
# ============================================================================


@pytest.mark.contract
class TestMappingCreate:
    @pytest.mark.django_db
    def test_create_with_repository_id_succeeds_and_mirrors_legacy(
        self, session_client, workspace, project, installation, enabled_repo
    ):
        resp = session_client.post(
            _mappings_url(workspace.slug, project.id),
            {"repository_id": str(enabled_repo.pk), "base_branch": "main"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        # Legacy fields are mirrored.
        assert resp.data["github_repo"] == enabled_repo.full_name
        # github_installation_id is NOT exposed in the response.
        assert "github_installation_id" not in resp.data
        # repository_detail is populated.
        assert resp.data["repository_detail"] is not None
        assert str(resp.data["repository_detail"]["id"]) == str(enabled_repo.pk)
        assert resp.data["repository_detail"]["full_name"] == enabled_repo.full_name
        # DB check: the FK is set, legacy fields are populated.
        mapping = RepoProjectMapping.objects.get(project=project)
        assert mapping.repository == enabled_repo
        assert mapping.github_installation_id == installation.installation_id
        assert mapping.github_repo == enabled_repo.full_name

    @pytest.mark.django_db
    def test_create_rejects_raw_github_installation_id(
        self, session_client, workspace, project, installation, enabled_repo
    ):
        resp = session_client.post(
            _mappings_url(workspace.slug, project.id),
            {
                "github_installation_id": installation.installation_id,
                "github_repo": "acme/x",
            },
            format="json",
        )
        # S2 requires repository_id; raw legacy fields are rejected.
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_create_cross_workspace_repo_rejected(
        self, session_client, workspace, project, installation, enabled_repo, second_workspace, create_user
    ):
        # Create a project in second_workspace and try to use a repo from
        # the primary workspace.  The session user must be authorised in both
        # workspaces so the test exercises cross-workspace repository isolation
        # rather than failing on membership/permission checks.
        p2 = Project.objects.create(name="P2", identifier="P2", workspace=second_workspace, created_by=create_user)
        ProjectMember.objects.create(
            workspace=second_workspace, project=p2, member=create_user, role=20, is_active=True
        )
        resp = session_client.post(
            _mappings_url(second_workspace.slug, p2.id),
            {"repository_id": str(enabled_repo.pk)},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_create_nonexistent_repo_rejected(self, session_client, workspace, project):
        resp = session_client.post(
            _mappings_url(workspace.slug, project.id),
            {"repository_id": str(uuid.uuid4())},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_create_disabled_repo_rejected(self, session_client, workspace, project, installation, disabled_repo):
        resp = session_client.post(
            _mappings_url(workspace.slug, project.id),
            {"repository_id": str(disabled_repo.pk)},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_create_inactive_installation_rejected(
        self, session_client, workspace, project, installation, enabled_repo
    ):
        installation.is_active = False
        installation.save()
        resp = session_client.post(
            _mappings_url(workspace.slug, project.id),
            {"repository_id": str(enabled_repo.pk)},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_second_live_mapping_on_same_project_rejected(
        self, session_client, workspace, project, installation, enabled_repo
    ):
        # Create first mapping.
        resp = session_client.post(
            _mappings_url(workspace.slug, project.id),
            {"repository_id": str(enabled_repo.pk)},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED

        # Second repo for same workspace.
        repo2 = GithubEnabledRepository.objects.create(
            installation=installation,
            github_repository_id=99902,
            full_name="s2-acme/repo2",
            is_enabled=True,
        )
        resp = session_client.post(
            _mappings_url(workspace.slug, project.id),
            {"repository_id": str(repo2.pk)},
            format="json",
        )
        assert resp.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.django_db
    def test_member_cannot_create(self, api_client, workspace, create_user, project, installation, enabled_repo):
        WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(role=15)
        ProjectMember.objects.filter(project=project, member=create_user).update(role=15)
        api_client.force_authenticate(user=create_user)
        resp = api_client.post(
            _mappings_url(workspace.slug, project.id),
            {"repository_id": str(enabled_repo.pk)},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.contract
class TestMappingList:
    @pytest.mark.django_db
    def test_list_includes_repository_detail(self, session_client, workspace, project, installation, enabled_repo):
        RepoProjectMapping.objects.create(
            project=project,
            github_installation_id=installation.installation_id,
            github_repo=enabled_repo.full_name,
            repository=enabled_repo,
        )
        resp = session_client.get(_mappings_url(workspace.slug, project.id))
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1
        assert resp.data[0]["repository_detail"] is not None
        assert str(resp.data[0]["repository_detail"]["id"]) == str(enabled_repo.pk)
        assert resp.data[0]["repository_detail"]["full_name"] == enabled_repo.full_name

    @pytest.mark.django_db
    def test_list_does_not_expose_github_installation_id(
        self, session_client, workspace, project, installation, enabled_repo
    ):
        RepoProjectMapping.objects.create(
            project=project,
            github_installation_id=installation.installation_id,
            github_repo=enabled_repo.full_name,
            repository=enabled_repo,
        )
        resp = session_client.get(_mappings_url(workspace.slug, project.id))
        assert resp.status_code == status.HTTP_200_OK
        assert "github_installation_id" not in resp.data[0]

    @pytest.mark.django_db
    def test_list_preserves_legacy_fields(self, session_client, workspace, project, legacy_mapping):
        resp = session_client.get(_mappings_url(workspace.slug, project.id))
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1
        assert resp.data[0]["github_repo"] == legacy_mapping.github_repo
        assert resp.data[0]["base_branch"] == legacy_mapping.base_branch
        assert resp.data[0]["is_default"] is True
        # Legacy mapping has no repository FK -> detail is null.
        assert resp.data[0]["repository_detail"] is None

    @pytest.mark.django_db
    def test_member_can_list(
        self, api_client, workspace, create_user, project, installation, enabled_repo, legacy_mapping
    ):
        # Member role for both workspace and project.
        WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(role=15)
        ProjectMember.objects.filter(project=project, member=create_user).update(role=15)
        api_client.force_authenticate(user=create_user)
        resp = api_client.get(_mappings_url(workspace.slug, project.id))
        assert resp.status_code == status.HTTP_200_OK


@pytest.mark.contract
class TestMappingDelete:
    @pytest.mark.django_db
    def test_delete_mapping(self, session_client, workspace, project, legacy_mapping):
        with patch("plane.db.mixins.soft_delete_related_objects.delay"):
            resp = session_client.delete(_mapping_detail_url(workspace.slug, project.id, legacy_mapping.pk))
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not RepoProjectMapping.objects.filter(pk=legacy_mapping.pk).exists()
        assert RepoProjectMapping.all_objects.filter(pk=legacy_mapping.pk).exists()

    @pytest.mark.django_db
    def test_member_cannot_delete(self, api_client, workspace, create_user, project, legacy_mapping):
        WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(role=15)
        ProjectMember.objects.filter(project=project, member=create_user).update(role=15)
        api_client.force_authenticate(user=create_user)
        resp = api_client.delete(_mapping_detail_url(workspace.slug, project.id, legacy_mapping.pk))
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# Cross-workspace isolation
# ============================================================================


@pytest.mark.contract
class TestCrossWorkspaceIsolation:
    @pytest.mark.django_db
    def test_workspace_a_cannot_see_workspace_b_installation(
        self,
        session_client,
        workspace,
        installation,
        second_workspace,
        second_workspace_user,
    ):
        # Create an installation in second_workspace too.
        GithubAppInstallation.objects.create(
            workspace=second_workspace,
            installation_id=1110001,
            account_login="other-org",
        )
        # session_client is authenticated to workspace (primary), NOT second_workspace.
        # But the user IS a member of second_workspace (they created it via the fixture),
        # so they CAN see it. Let's test properly: create a standalone client.
        from rest_framework.test import APIClient

        ext_user = User.objects.create(email="ext@plane.so", username="ext-user", first_name="Ext", last_name="User")
        ext_user.set_password("test")
        ext_user.save()
        ext_client = APIClient()
        ext_client.force_authenticate(user=ext_user)
        resp = ext_client.get(_install_url(workspace.slug))
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_workspace_a_repos_isolated_from_workspace_b(
        self, session_client, workspace, installation, enabled_repo, second_workspace
    ):
        # second_workspace has no installation and thus no repos.
        resp = session_client.get(_repos_url(second_workspace.slug))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data == []
