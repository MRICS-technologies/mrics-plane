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

from plane.db.models import Issue, Project, ProjectMember, Workspace, WorkspaceMember
from plane.db.models.integration.github_sync import GithubWebhookDelivery, IssueGitLink, RepoProjectMapping
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



def _configure_webhook_app(secret="test-webhook-secret"):
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
    return secret


def _pull_request_payload(
    installation,
    repository,
    number=17,
    title="TP-1 implement webhook",
    head="feature/TP-1-webhook",
    action="opened",
    merged=False,
    updated_at="2026-07-31T00:00:00Z",
):
    return {
        "action": action,
        "installation": {"id": installation.installation_id},
        "repository": {"id": repository.github_repository_id, "full_name": repository.full_name},
        "pull_request": {
            "number": number,
            "title": title,
            "head": {"ref": head},
            "html_url": f"https://github.example/{repository.full_name}/pull/{number}",
            "merged": merged,
            "updated_at": updated_at,
        },
    }


def _post_signed_webhook(api_client, payload, secret, delivery_id):
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return api_client.post(
        TestGitHubWebhookAPI.WEBHOOK_URL,
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
        HTTP_X_GITHUB_EVENT="pull_request",
        HTTP_X_GITHUB_DELIVERY=delivery_id,
    )


@pytest.fixture
def webhook_context(db, workspace, project, issue):
    issue.sequence_id = 1
    issue.save(update_fields=["sequence_id"])
    installation = GithubAppInstallation.objects.create(
        workspace=workspace, installation_id=92001, account_login="acme"
    )
    repository = GithubEnabledRepository.objects.create(
        installation=installation,
        github_repository_id=93001,
        full_name="acme/widgets",
        is_enabled=True,
    )
    RepoProjectMapping.objects.create(
        workspace=workspace,
        project=project,
        repository=repository,
        github_installation_id=installation.installation_id,
        github_repo=repository.full_name,
    )
    return installation, repository


@pytest.mark.contract
class TestGitHubPullRequestWebhookContract:
    @pytest.mark.django_db
    def test_raw_signature_and_body_limit(self, api_client, webhook_context):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        response = _post_signed_webhook(
            api_client,
            _pull_request_payload(installation, repository, title="no issue key"),
            secret,
            "delivery-raw-signature",
        )
        assert response.status_code == status.HTTP_200_OK
        assert GithubWebhookDelivery.objects.filter(delivery_id="delivery-raw-signature").count() == 1

        # This must return before calling the HMAC/configuration path or JSON parser.
        response = api_client.post(
            TestGitHubWebhookAPI.WEBHOOK_URL,
            data=b"x" * (1024 * 1024 + 1),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE

    @pytest.mark.django_db
    def test_duplicate_delivery_is_acknowledged_without_reprocessing(self, api_client, webhook_context):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        payload = _pull_request_payload(installation, repository)
        response = _post_signed_webhook(api_client, payload, secret, "delivery-duplicate")
        assert response.status_code == status.HTTP_200_OK
        link = IssueGitLink.objects.get(kind="pr", github_repo=repository.full_name, pr_number=17)
        assert link.state == "open"

        payload["action"] = "closed"
        payload["pull_request"]["merged"] = True
        response = _post_signed_webhook(api_client, payload, secret, "delivery-duplicate")
        assert response.status_code == status.HTTP_200_OK
        link.refresh_from_db()
        assert link.state == "open"
        assert GithubWebhookDelivery.objects.filter(delivery_id="delivery-duplicate").count() == 1

    @pytest.mark.django_db
    def test_inactive_or_wrong_repository_does_not_link(self, api_client, webhook_context):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        installation.is_active = False
        installation.save(update_fields=["is_active"])
        response = _post_signed_webhook(
            api_client, _pull_request_payload(installation, repository), secret, "delivery-inactive"
        )
        assert response.status_code == status.HTTP_200_OK
        assert not IssueGitLink.objects.filter(kind="pr").exists()

        installation.is_active = True
        installation.save(update_fields=["is_active"])
        payload = _pull_request_payload(installation, repository, number=18)
        payload["repository"]["id"] = repository.github_repository_id + 1
        response = _post_signed_webhook(api_client, payload, secret, "delivery-wrong-repo")
        assert response.status_code == status.HTTP_200_OK
        assert not IssueGitLink.objects.filter(kind="pr").exists()

    @pytest.mark.django_db
    def test_branch_match_wins_and_events_are_idempotent_and_ordered(self, api_client, webhook_context, project, issue):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        branch_issue = Issue.objects.create(
            name="Branch Issue",
            project=project,
            workspace=project.workspace,
            created_by=issue.created_by,
            sequence_id=2,
        )
        IssueGitLink.objects.create(
            workspace=project.workspace,
            project=project,
            issue=branch_issue,
            github_repo=repository.full_name,
            kind="branch",
            ref="feature/linked-branch",
            url="https://github.example/acme/widgets/tree/feature/linked-branch",
            state="open",
            detected_via="manual",
        )
        payload = _pull_request_payload(
            installation,
            repository,
            title="TP-1 title fallback must lose",
            head="feature/linked-branch",
            updated_at="2026-07-31T01:00:00Z",
        )
        assert _post_signed_webhook(api_client, payload, secret, "delivery-open").status_code == status.HTTP_200_OK
        link = IssueGitLink.objects.get(kind="pr", github_repo=repository.full_name, pr_number=17)
        assert link.issue_id == branch_issue.id
        assert link.detected_via == "branch"
        assert link.state == "open"

        payload.update(action="closed")
        payload["pull_request"].update(merged=True, updated_at="2026-07-31T02:00:00Z")
        assert _post_signed_webhook(api_client, payload, secret, "delivery-merged").status_code == status.HTTP_200_OK
        link.refresh_from_db()
        assert link.state == "merged"

        payload["pull_request"].update(merged=False, updated_at="2026-07-31T00:30:00Z")
        assert _post_signed_webhook(api_client, payload, secret, "delivery-stale").status_code == status.HTTP_200_OK
        link.refresh_from_db()
        assert link.state == "merged"

        payload.update(action="reopened")
        payload["pull_request"].update(merged=False, updated_at="2026-07-31T03:00:00Z")
        assert _post_signed_webhook(api_client, payload, secret, "delivery-reopened").status_code == status.HTTP_200_OK
        link.refresh_from_db()
        assert link.state == "open"

    @pytest.mark.django_db
    def test_issue_key_no_match_and_cross_workspace_mapping_are_safe(self, api_client, webhook_context, create_user):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        payload = _pull_request_payload(
            installation, repository, title="TP-999 only outside issue", head="release/no-key", number=19
        )
        assert _post_signed_webhook(api_client, payload, secret, "delivery-no-match").status_code == status.HTTP_200_OK
        assert not IssueGitLink.objects.filter(kind="pr").exists()

        second_workspace = Workspace.objects.create(
            name="Other Workspace", slug="other-webhook-workspace", owner=create_user
        )
        WorkspaceMember.objects.create(workspace=second_workspace, member=create_user, role=20)
        second_project = Project.objects.create(
            name="Other Project", identifier="TP", workspace=second_workspace, created_by=create_user
        )
        second_issue = Issue.objects.create(
            name="Other Issue",
            project=second_project,
            workspace=second_workspace,
            created_by=create_user,
            sequence_id=999,
        )
        RepoProjectMapping.objects.create(
            workspace=second_workspace,
            project=second_project,
            repository=repository,
            github_installation_id=installation.installation_id,
            github_repo=repository.full_name,
        )
        assert (
            _post_signed_webhook(api_client, payload, secret, "delivery-cross-workspace").status_code
            == status.HTTP_200_OK
        )
        assert not IssueGitLink.objects.filter(kind="pr", issue=second_issue).exists()


    @pytest.mark.django_db
    def test_existing_pr_updates_without_a_current_issue_key(self, api_client, webhook_context):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        payload = _pull_request_payload(installation, repository, number=20, title="TP-1 initial")
        assert (
            _post_signed_webhook(api_client, payload, secret, "delivery-existing-open").status_code
            == status.HTTP_200_OK
        )
        payload.update(action="closed")
        payload["pull_request"].update(
            title="release housekeeping",
            head={"ref": "release/no-key"},
            merged=False,
            updated_at="2026-07-31T03:00:00Z",
        )
        assert (
            _post_signed_webhook(api_client, payload, secret, "delivery-existing-close").status_code
            == status.HTTP_200_OK
        )
        link = IssueGitLink.objects.get(kind="pr", github_repo=repository.full_name, pr_number=20)
        assert link.state == "closed"
        assert link.ref == "release/no-key"

        synchronize = _pull_request_payload(
            installation, repository, number=22, title="TP-1 synchronize", action="synchronize"
        )
        assert (
            _post_signed_webhook(api_client, synchronize, secret, "delivery-sync-initial").status_code
            == status.HTTP_200_OK
        )
        assert IssueGitLink.objects.get(kind="pr", github_repo=repository.full_name, pr_number=22).state == "open"

    @pytest.mark.django_db
    def test_pr_identity_is_scoped_to_workspace(self, api_client, webhook_context, create_user):
        installation, repository = webhook_context
        secret = _configure_webhook_app()
        second_workspace = Workspace.objects.create(
            name="Separate Workspace", slug="separate-webhook-workspace", owner=create_user
        )
        WorkspaceMember.objects.create(workspace=second_workspace, member=create_user, role=20)
        second_project = Project.objects.create(
            name="Separate Project", identifier="ZZ", workspace=second_workspace, created_by=create_user
        )
        second_issue = Issue.objects.create(
            name="Separate Issue",
            project=second_project,
            workspace=second_workspace,
            created_by=create_user,
            sequence_id=1,
        )
        IssueGitLink.objects.create(
            workspace=second_workspace,
            project=second_project,
            issue=second_issue,
            github_repo=repository.full_name,
            kind="pr",
            ref="old-ref",
            url="https://github.example/acme/widgets/pull/21",
            state="open",
            pr_number=21,
            detected_via="title",
        )
        payload = _pull_request_payload(installation, repository, number=21, title="TP-1 current workspace")
        assert (
            _post_signed_webhook(api_client, payload, secret, "delivery-workspace-scoped").status_code
            == status.HTTP_200_OK
        )
        current_link = IssueGitLink.objects.get(
            workspace=installation.workspace, kind="pr", github_repo=repository.full_name, pr_number=21
        )
        assert current_link.issue.workspace_id == installation.workspace_id
        foreign_link = IssueGitLink.objects.get(workspace=second_workspace, kind="pr", pr_number=21)
        assert foreign_link.issue_id == second_issue.id
