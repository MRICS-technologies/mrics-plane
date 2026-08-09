# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for the native GitHub sync endpoints (Phase 3 MVP).

GET/POST   /api/workspaces/<slug>/projects/<project_id>/github/mappings/
DELETE     /api/workspaces/<slug>/projects/<project_id>/github/mappings/<pk>/
GET        /api/workspaces/<slug>/projects/<project_id>/issues/<issue_id>/git-links/
POST       /api/workspaces/<slug>/projects/<project_id>/issues/<issue_id>/github/create-branch/
POST       /api/github/webhook/

The webhook secret and app credentials used below are sourced from the P1
instance `InstanceConfiguration` (`GITHUB_APP_*` keys), not environment
variables -- see `plane.services.github.credentials`.
"""

import hashlib
import hmac
import json

import pytest
from rest_framework import status

from plane.db.models import Issue, Project, ProjectMember
from plane.db.models.integration.github_sync import RepoProjectMapping
from plane.db.models.integration.github_app import GithubAppInstallation, GithubEnabledRepository
from plane.license.models import InstanceConfiguration
from plane.license.utils.encryption import encrypt_data


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(
        name="Test Project",
        identifier="TP",
        workspace=workspace,
        created_by=create_user,
    )
    ProjectMember.objects.create(
        workspace=workspace,
        project=project,
        member=create_user,
        role=20,
        is_active=True,
    )
    return project


@pytest.fixture
def issue(db, project, create_user):
    return Issue.objects.create(
        name="Test Issue",
        project=project,
        workspace=project.workspace,
        created_by=create_user,
    )


@pytest.fixture
def mapping(db, project):
    return RepoProjectMapping.objects.create(
        project=project,
        github_installation_id=123,
        github_repo="acme/widgets",
    )


def _mappings_url(slug, project_id):
    return f"/api/workspaces/{slug}/projects/{project_id}/github/mappings/"


def _create_branch_url(slug, project_id, issue_id):
    return f"/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/github/create-branch/"


@pytest.mark.contract
class TestRepoProjectMappingAPI:
    @pytest.mark.django_db
    def test_list_and_create_mapping(self, session_client, workspace, project):
        # S2: must create native installation + enabled repository first.
        installation = GithubAppInstallation.objects.create(
            workspace=workspace,
            installation_id=42,
            account_login="acme",
        )
        enabled_repo = GithubEnabledRepository.objects.create(
            installation=installation,
            github_repository_id=1001,
            full_name="acme/widgets",
            is_enabled=True,
        )

        url = _mappings_url(workspace.slug, project.id)

        response = session_client.post(
            url,
            {"repository_id": str(enabled_repo.pk)},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data

        response = session_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1


@pytest.mark.contract
class TestIssueCreateBranchAPI:
    @pytest.mark.django_db
    def test_create_branch_without_mapping_returns_422(self, session_client, workspace, project, issue):
        url = _create_branch_url(workspace.slug, project.id, issue.id)

        response = session_client.post(url, {"branch_name": "feature/TP-1-add-login"}, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.django_db
    def test_create_branch_without_github_app_configured_returns_422(
        self, session_client, workspace, project, issue, mapping
    ):
        # Mapping exists, but no GITHUB_APP_* InstanceConfiguration has been
        # written -- the credentials bridge must report unconfigured rather
        # than falling back to any environment variable.
        url = _create_branch_url(workspace.slug, project.id, issue.id)

        response = session_client.post(url, {"branch_name": "feature/TP-1-add-login"}, format="json")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.data["error"] == "GitHub App is not configured"


def _set_github_app_webhook_secret(secret):
    InstanceConfiguration.objects.update_or_create(
        key="GITHUB_APP_WEBHOOK_SECRET",
        defaults={"value": encrypt_data(secret), "category": "GITHUB_APP", "is_encrypted": True},
    )


@pytest.mark.contract
class TestGitHubWebhookAPI:
    WEBHOOK_URL = "/api/github/webhook/"

    @pytest.mark.django_db
    def test_webhook_invalid_signature_returns_401(self, api_client):
        _set_github_app_webhook_secret("test-webhook-secret")

        response = api_client.post(
            self.WEBHOOK_URL,
            data=json.dumps({"action": "opened"}),
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256="sha256=bogus",
            HTTP_X_GITHUB_EVENT="pull_request",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_webhook_valid_signature_returns_200(self, api_client):
        secret = "test-webhook-secret"
        _set_github_app_webhook_secret(secret)
        InstanceConfiguration.objects.update_or_create(
            key="GITHUB_APP_ID",
            defaults={"value": "123456", "category": "GITHUB_APP", "is_encrypted": False},
        )
        InstanceConfiguration.objects.update_or_create(
            key="GITHUB_APP_PRIVATE_KEY",
            defaults={
                "value": encrypt_data("fake-pem-private-key"),
                "category": "GITHUB_APP",
                "is_encrypted": True,
            },
        )

        body = json.dumps({"action": "opened"}).encode()
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        response = api_client.post(
            self.WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=signature,
            HTTP_X_GITHUB_EVENT="pull_request",
        )

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.django_db
    def test_webhook_without_github_app_configured_returns_401(self, api_client):
        # No GITHUB_APP_WEBHOOK_SECRET row at all -- must fail closed.
        body = json.dumps({"action": "opened"}).encode()
        signature = "sha256=" + hmac.new(b"any-secret", body, hashlib.sha256).hexdigest()

        response = api_client.post(
            self.WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=signature,
            HTTP_X_GITHUB_EVENT="pull_request",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_webhook_with_partial_app_configuration_returns_401(self, api_client):
        # A webhook secret with no app id/private key is not a usable GitHub
        # App -- must still fail closed rather than accept the signature.
        secret = "test-webhook-secret"
        _set_github_app_webhook_secret(secret)

        body = json.dumps({"action": "opened"}).encode()
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        response = api_client.post(
            self.WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=signature,
            HTTP_X_GITHUB_EVENT="pull_request",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
