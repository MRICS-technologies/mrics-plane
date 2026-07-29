# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for the native GitHub sync endpoints (Phase 3 MVP).

GET/POST   /api/workspaces/<slug>/projects/<project_id>/github/mappings/
DELETE     /api/workspaces/<slug>/projects/<project_id>/github/mappings/<pk>/
GET        /api/workspaces/<slug>/projects/<project_id>/issues/<issue_id>/git-links/
POST       /api/workspaces/<slug>/projects/<project_id>/issues/<issue_id>/github/create-branch/
POST       /api/github/webhook/
"""

import hashlib
import hmac
import json

import pytest
from rest_framework import status

from plane.db.models import Issue, Project, ProjectMember
from plane.db.models.integration.github_sync import RepoProjectMapping


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
        url = _mappings_url(workspace.slug, project.id)

        response = session_client.post(
            url,
            {"github_installation_id": 42, "github_repo": "acme/widgets"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

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


@pytest.mark.contract
class TestGitHubWebhookAPI:
    WEBHOOK_URL = "/api/github/webhook/"

    @pytest.mark.django_db
    def test_webhook_invalid_signature_returns_401(self, api_client, settings):
        settings_secret = "test-webhook-secret"
        import os

        os.environ["GITHUB_WEBHOOK_SECRET"] = settings_secret

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
        import os

        secret = "test-webhook-secret"
        os.environ["GITHUB_WEBHOOK_SECRET"] = secret

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
